"""Original IELTS-style practice items and links to official public samples.

Official question text is not copied into this repository. The linked pages are
published by IELTS and the British Council; original items below are ours.
"""

ACADEMIC_SAMPLES = "https://ielts.org/take-a-test/preparation-resources/sample-test-questions/academic-test"
GENERAL_SAMPLES = "https://ielts.org/take-a-test/preparation-resources/sample-test-questions/general-training-test"
FAMILIARISATION = "https://takeielts.britishcouncil.org/prepare/ielts-free-practice-mock-tests/ielts-familiarisation-test"

# exam, skill, task_type, title, prompt, answer_key, topic, source_kind, source_url
# In-app practice items live in backend/content as structured tests.
QUESTIONS = [
    ("IELTS", "listening", "Official public samples", "IELTS official Listening sample tasks", None, None, "official", "OFFICIAL_LINK", ACADEMIC_SAMPLES),
    ("IELTS", "reading", "Official public samples", "IELTS official Academic Reading sample tasks", None, None, "official", "OFFICIAL_LINK", ACADEMIC_SAMPLES),
    ("IELTS", "writing", "Official public samples", "IELTS official Academic Writing sample tasks", None, None, "official", "OFFICIAL_LINK", ACADEMIC_SAMPLES),
    ("IELTS", "speaking", "Official public samples", "IELTS official Speaking sample tasks", None, None, "official", "OFFICIAL_LINK", ACADEMIC_SAMPLES),
    ("IELTS", "reading", "Official public samples", "IELTS General Training Reading samples", None, None, "official", "OFFICIAL_LINK", GENERAL_SAMPLES),
    ("IELTS", "writing", "Official public samples", "IELTS General Training Writing samples", None, None, "official", "OFFICIAL_LINK", GENERAL_SAMPLES),
    ("IELTS", "reading", "Official familiarisation", "British Council computer test familiarisation", None, None, "official", "OFFICIAL_LINK", FAMILIARISATION),
]
