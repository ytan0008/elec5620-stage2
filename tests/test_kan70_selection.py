"""Selection is based on the learner's own released, same-exam evidence."""
import random

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.auth import token_for
from backend.config import settings
from backend.db import Base, get_db
from backend.main import app
from backend.models import (AgentEvent, Escalation, InstructorDecision, MockExam, Plan, Practice, Profile,
                            QuestionItem, ResultPackage, Submission, User)
from backend.practice_selection import PREFERENCES, active_plan_context, recent_weaknesses, select_question


@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def add_user(db, email):
    user = User(email=email, name='Test learner', password_hash='not-a-real-hash', role='learner')
    db.add(user)
    db.flush()
    return user


def add_assessment(db, user, exam, skill, criteria, state='RELEASED'):
    practice = Practice(user_id=user.id, exam=exam, skill=skill, prompt={'content_id': 'source-task'})
    package = ResultPackage(user_id=user.id, kind=skill, state=state, payload={'criteria': criteria},
                            confidence={key: .8 for key in criteria}, source_mode='LOCAL', issues=[])
    db.add_all([practice, package])
    db.flush()
    db.add(Submission(user_id=user.id, practice_id=practice.id, package_id=package.id,
                      text='An example response used to test selection.', attempt=1))
    db.flush()


def add_mock(db, user, exam, writing, speaking, state='RELEASED'):
    package = ResultPackage(user_id=user.id, kind='mock_exam', state=state,
        payload={'score_scale': f'{exam} scale', 'details': {
            'writing': {'task1': {'criteria': writing}}, 'speaking': {'criteria': speaking}}},
        confidence={'writing': .8, 'speaking': .8}, source_mode='LOCAL', issues=[])
    db.add(package)
    db.flush()
    db.add(MockExam(user_id=user.id, exam=exam, status='SUBMITTED', sections={}, package_id=package.id))
    db.flush()
    return package


def add_plan(db, user, exam, *, state='RELEASED'):
    package = ResultPackage(user_id=user.id, kind='plan', state=state, payload={},
                            confidence={'plan': .8}, source_mode='LOCAL', issues=[])
    db.add(package)
    db.flush()
    content = {'title': 'IELTS starter plan', 'priorities': ['writing'],
               'activities': [{'skill': 'writing', 'title': 'Grammar task 1', 'reason': 'Target grammar'}]}
    if exam is not None:
        content['exam'] = exam
    plan = Plan(user_id=user.id, package_id=package.id, version=1, status='ACTIVE', content=content)
    db.add(plan)
    db.flush()
    return plan


@pytest.fixture
def api(db, monkeypatch):
    # The application's lifespan seeds its normal database. Override the
    # dependency and avoid lifespan so this integration test stays isolated.
    monkeypatch.setenv('DEMO_MODE', 'true')
    settings.cache_clear()
    previous = dict(app.dependency_overrides)
    def isolated_db():
        yield db
    app.dependency_overrides[get_db] = isolated_db
    client = TestClient(app)
    yield client
    client.close()
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
    settings.cache_clear()


def add_profile(db, user, proficiency='intermediate'):
    db.add(Profile(user_id=user.id, exam='IELTS', proficiency=proficiency, target_score=7,
                   exam_date='2027-12-15', weekly_hours=6, priority_skills=['writing', 'speaking']))
    db.flush()


@pytest.mark.parametrize('skill', ['writing', 'speaking'])
def test_weaknesses_use_only_owned_released_assessments_for_same_exam_and_skill(db, skill):
    user = add_user(db, f'{skill}@example.com')
    other = add_user(db, f'other-{skill}@example.com')
    add_assessment(db, user, 'IELTS', skill, {'grammar': 4, 'lexical_resource': 8})
    add_assessment(db, user, 'IELTS', skill, {'grammar': 8, 'lexical_resource': 0}, state='HELD')
    add_assessment(db, other, 'IELTS', skill, {'lexical_resource': 0})
    add_assessment(db, user, 'TOEFL', skill, {'language_use': 1})
    other_skill = 'speaking' if skill == 'writing' else 'writing'
    add_assessment(db, user, 'IELTS', other_skill, {'lexical_resource': 0})

    assert recent_weaknesses(db, user.id, 'IELTS', skill, 7) == ['grammar']


def test_weaknesses_are_ordered_by_score_and_empty_when_no_scores_are_below_target(db):
    user = add_user(db, 'rank@example.com')
    add_assessment(db, user, 'IELTS', 'writing', {'grammar': 4, 'coherence': 6, 'lexical_resource': 8})
    assert recent_weaknesses(db, user.id, 'IELTS', 'writing', 7) == ['grammar', 'coherence']
    assert recent_weaknesses(db, user.id, 'IELTS', 'writing', 4) == []
    assert recent_weaknesses(db, user.id, 'IELTS', 'speaking', 7) == []


def test_only_recent_attempts_influence_weaknesses(db):
    user = add_user(db, 'recent@example.com')
    add_assessment(db, user, 'IELTS', 'writing', {'grammar': 1})
    for _ in range(5):
        add_assessment(db, user, 'IELTS', 'writing', {'grammar': 8})
    assert recent_weaknesses(db, user.id, 'IELTS', 'writing', 7) == []


def test_toefl_invalid_zero_score_does_not_become_a_weakness(db):
    user = add_user(db, 'invalid-toefl@example.com')
    add_assessment(db, user, 'TOEFL', 'speaking', {'language_use': 0, 'topic_development': 5})
    assert recent_weaknesses(db, user.id, 'TOEFL', 'speaking', 4) == []


def test_mock_criteria_are_used_only_when_owned_released_and_same_exam(db):
    user = add_user(db, 'mock@example.com')
    other = add_user(db, 'other-mock@example.com')
    add_mock(db, user, 'IELTS', {'grammar': 4, 'lexical_resource': 8}, {'fluency': 4, 'grammar': 8})
    add_mock(db, user, 'IELTS', {'lexical_resource': 0}, {'grammar': 0}, state='HELD')
    add_mock(db, other, 'IELTS', {'lexical_resource': 0}, {'grammar': 0})
    add_mock(db, user, 'TOEFL', {'language_use': 1}, {'language_use': 1})
    assert recent_weaknesses(db, user.id, 'IELTS', 'writing', 7) == ['grammar']
    assert recent_weaknesses(db, user.id, 'IELTS', 'speaking', 7) == ['fluency']


def test_recent_limit_applies_across_practice_and_mock_results(db):
    user = add_user(db, 'mixed-recent@example.com')
    add_assessment(db, user, 'IELTS', 'writing', {'grammar': 1})  # old low score
    for _ in range(4):
        add_assessment(db, user, 'IELTS', 'writing', {'grammar': 8})
    add_mock(db, user, 'IELTS', {'grammar': 8}, {'fluency': 8})
    assert recent_weaknesses(db, user.id, 'IELTS', 'writing', 7) == []


def test_teacher_corrected_mock_details_are_not_treated_as_verified_criteria(db):
    user = add_user(db, 'corrected-mock@example.com')
    instructor = add_user(db, 'teacher@example.com')
    package = add_mock(db, user, 'IELTS', {'grammar': 2}, {'fluency': 2})
    case = Escalation(package_id=package.id, status='RESOLVED', reason='Score corrected')
    db.add(case)
    db.flush()
    db.add(InstructorDecision(case_id=case.id, instructor_id=instructor.id, decision='correct',
                              note='Teacher changed the section score', correction={'section_scores': {'writing': 8}}))
    db.flush()
    assert recent_weaknesses(db, user.id, 'IELTS', 'writing', 7) == []
    assert recent_weaknesses(db, user.id, 'IELTS', 'speaking', 7) == []


@pytest.mark.parametrize('plan_exam,state,expected_active', [
    ('IELTS', 'RELEASED', True), ('TOEFL', 'RELEASED', False),
    (None, 'RELEASED', False), ('IELTS', 'HELD', False),
])
def test_active_plan_must_be_released_and_have_proven_same_exam(db, plan_exam, state, expected_active):
    user = add_user(db, 'plan-context@example.com')
    add_plan(db, user, plan_exam, state=state)
    context = active_plan_context(db, user.id, 'IELTS', 'writing')
    assert context['active'] is expected_active
    if expected_active:
        assert context['skill_priority'] and context['task'] == 'task1' and context['focus'] == ['grammar']
    else:
        assert context['focus'] == [] and context['task'] is None


@pytest.mark.parametrize('question_id', ['toefl-speaking-campus', 'toefl-speaking-volunteer', 'toefl-speaking-transport'])
def test_each_toefl_speaking_test_completes_repeat_and_interview(question_id):
    from backend import examiner
    from backend.content import SPEAKING
    test = SPEAKING[question_id]
    state, prompt, view = examiner.start(test, 'boy')
    assert prompt and view['stage'] == 'repeat'
    stages = []
    for _ in range(len(test['repeat']) + len(test['interview']['questions'])):
        stage = state['stage']
        stages.append(stage)
        answer = test['repeat'][state['i']]['text'] if stage == 'repeat' else 'I prefer this approach because it helps people and offers useful opportunities.'
        state, text, view, done, meta = examiner.advance(test, state, answer)
        assert text and view
    assert stages.count('repeat') == len(test['repeat'])
    assert stages.count('interview') == len(test['interview']['questions'])
    assert done and state['stage'] == 'done'
    assert len(state['scores']) == len(test['repeat']) and all(score == 1 for score in state['scores'])


@pytest.mark.parametrize('skill', ['writing', 'speaking'])
def test_beginner_and_advanced_get_matching_but_distinct_suggested_tasks(skill):
    beginner, beginner_info = select_question('IELTS', skill, set(), 'beginner', [], rng=random.Random(4))
    advanced, advanced_info = select_question('IELTS', skill, set(), 'advanced', [], rng=random.Random(4))
    assert beginner['id'] != advanced['id']
    assert 'beginner' in PREFERENCES[beginner['id']][0].split()
    assert 'advanced' in PREFERENCES[advanced['id']][0].split()
    assert beginner_info['profile_level'] == 'beginner' and advanced_info['profile_level'] == 'advanced'
    assert 'not official' in beginner_info['rationale']


@pytest.mark.parametrize('skill', ['writing', 'speaking'])
def test_recent_criterion_changes_question_selection(skill):
    # The two writing task-1 items serve both criteria; excluding them makes
    # the distinct targeting observable instead of depending on random ties.
    avoid = {'ielts-writing-t1-library', 'ielts-writing-t1-commute'} if skill == 'writing' else set()
    grammar, grammar_info = select_question('IELTS', skill, avoid, 'intermediate', ['grammar'], rng=random.Random(4))
    lexical, lexical_info = select_question('IELTS', skill, avoid, 'intermediate', ['lexical_resource'], rng=random.Random(4))
    assert grammar['id'] != lexical['id']
    assert 'grammar' in PREFERENCES[grammar['id']][1].split()
    assert 'lexical_resource' in PREFERENCES[lexical['id']][1].split()
    assert grammar_info['focus'] == 'grammar' and lexical_info['focus'] == 'lexical_resource'


@pytest.mark.parametrize('skill', ['writing', 'speaking'])
def test_unseen_item_is_chosen_even_when_preferred_items_have_been_seen(skill):
    from backend import content
    pool = content.WRITING if skill == 'writing' else content.SPEAKING
    ielts = [item for item in pool.values() if item['exam'] == 'IELTS']
    remaining = next(item for item in ielts if 'advanced' in PREFERENCES[item['id']][0].split()
                     and 'beginner' not in PREFERENCES[item['id']][0].split())
    seen = {item['id'] for item in ielts if item['id'] != remaining['id']}
    item, info = select_question('IELTS', skill, seen, 'beginner', ['grammar'], rng=random.Random(4))
    assert item['id'] == remaining['id'] and info['variety'] == 'unseen'


def test_active_plan_task_type_can_influence_question_selection():
    plan = {'active': True, 'skill_priority': True, 'focus': [], 'task': 'task1'}
    item, _ = select_question('IELTS', 'writing', set(), 'intermediate', [], rng=random.Random(4), plan_focus=plan)
    assert item['task'] == 'task1'


@pytest.mark.parametrize('skill,focus', [('writing', 'organisation'), ('speaking', 'topic_development')])
def test_toefl_uses_its_own_rubric_and_question_pool(skill, focus):
    item, info = select_question('TOEFL', skill, set(), 'advanced', [focus], rng=random.Random(4))
    assert item['exam'] == 'TOEFL' and item['kind'] == skill
    assert focus in PREFERENCES[item['id']][1].split() and info['focus'] == focus


def test_writing_and_live_speaking_api_receive_the_correct_personalisation(api, db):
    user = add_user(db, 'api@example.com')
    add_profile(db, user, 'advanced')
    add_assessment(db, user, 'IELTS', 'writing', {'grammar': 4, 'lexical_resource': 8})
    add_assessment(db, user, 'IELTS', 'speaking', {'fluency': 4, 'grammar': 8})
    # A held result must not change the focus returned to the learner.
    add_assessment(db, user, 'IELTS', 'writing', {'lexical_resource': 0}, state='HELD')
    db.commit()
    headers = {'Authorization': 'Bearer ' + token_for(user)}

    writing = api.post('/api/practice/writing', headers=headers)
    assert writing.status_code == 200, writing.text
    writing_body = writing.json()
    assert writing_body['prompt']['selection']['profile_level'] == 'advanced'
    assert writing_body['prompt']['selection']['focus'] == 'grammar'
    assert writing_body['prompt']['selection']['evidence_count'] == 1
    assert db.get(Practice, writing_body['id']).prompt['selection']['focus'] == 'grammar'

    speaking = api.post('/api/speaking/sessions', headers=headers, json={'persona': 'boy'})
    assert speaking.status_code == 200, speaking.text
    speaking_body = speaking.json()
    assert speaking_body['selection']['profile_level'] == 'advanced'
    assert speaking_body['selection']['focus'] == 'fluency'
    assert speaking_body['selection']['evidence_count'] == 1
    assert db.get(Practice, speaking_body['practice_id']).prompt['selection']['focus'] == 'fluency'
    later = api.get(f"/api/speaking/sessions/{speaking_body['id']}", headers=headers)
    assert later.status_code == 200 and later.json()['selection'] == speaking_body['selection']
    turn = api.post(f"/api/speaking/sessions/{speaking_body['id']}/turn", headers=headers,
                    json={'text': 'My name is Test Learner.', 'seconds': 3})
    assert turn.status_code == 200 and turn.json()['selection'] == speaking_body['selection']
    events = db.query(AgentEvent).filter_by(user_id=user.id, workflow='writing').all()
    assert any((event.detail or {}).get('selection', {}).get('focus') == 'grammar' for event in events)


def test_manual_question_bank_choice_is_not_replaced_by_personalisation(api, db):
    from backend.content import WRITING
    user = add_user(db, 'manual@example.com')
    add_profile(db, user, 'beginner')
    item = WRITING['ielts-writing-t2-ai']
    question = QuestionItem(exam='IELTS', skill='writing', task_type='Task 2', title=item['title'],
                            prompt=item['prompt'], topic=item['topic'], source_kind='ORIGINAL', content=item)
    db.add(question)
    db.commit()
    response = api.post(f'/api/practice/writing?question_id={question.id}',
                        headers={'Authorization': 'Bearer ' + token_for(user)})
    assert response.status_code == 200, response.text
    assert response.json()['prompt']['content_id'] == item['id']


def test_manual_and_mock_speaking_do_not_claim_automatic_selection(api, db):
    from backend.content import SPEAKING
    user = add_user(db, 'manual-speaking@example.com')
    add_profile(db, user, 'beginner')
    item = SPEAKING['ielts-speaking-4']
    question = QuestionItem(exam='IELTS', skill='speaking', task_type='Full speaking test', title=item['title'],
                            prompt='Speaking task selected by learner', topic=item['topic'], source_kind='ORIGINAL', content=item)
    mock = MockExam(user_id=user.id, exam='IELTS', status='IN_PROGRESS', sections={'speaking': {'test': item}})
    db.add_all([question, mock])
    db.commit()
    headers = {'Authorization': 'Bearer ' + token_for(user)}
    manual = api.post('/api/speaking/sessions', headers=headers, json={'question_id': question.id})
    assert manual.status_code == 200, manual.text
    assert manual.json()['test_title'] == item['title'] and 'selection' not in manual.json()
    automatic_mock = api.post('/api/speaking/sessions', headers=headers, json={'mock_id': mock.id})
    assert automatic_mock.status_code == 200, automatic_mock.text
    assert automatic_mock.json()['test_title'] == item['title'] and 'selection' not in automatic_mock.json()


@pytest.mark.parametrize('skill', ['writing', 'speaking'])
def test_selection_keeps_requested_exam_and_all_seen_fallback(skill):
    first, _ = select_question('IELTS', skill, set(), 'intermediate', [], rng=random.Random(4))
    assert first['exam'] == 'IELTS' and first['kind'] == skill
    # Once every available question has been seen, selection must still work.
    from backend import content
    pool = content.WRITING if skill == 'writing' else content.SPEAKING
    seen = {item['id'] for item in pool.values() if item['exam'] == 'IELTS'}
    again, _ = select_question('IELTS', skill, seen, 'intermediate', [], rng=random.Random(4))
    assert again['id'] in seen and again['exam'] == 'IELTS' and again['kind'] == skill
