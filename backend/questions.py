"""Original IELTS-style practice items and links to official public samples.

Official question text is not copied into this repository. The linked pages are
published by IELTS and the British Council; original items below are ours.
"""

ACADEMIC_SAMPLES = "https://ielts.org/take-a-test/preparation-resources/sample-test-questions/academic-test"
GENERAL_SAMPLES = "https://ielts.org/take-a-test/preparation-resources/sample-test-questions/general-training-test"
FAMILIARISATION = "https://takeielts.britishcouncil.org/prepare/ielts-free-practice-mock-tests/ielts-familiarisation-test"

# exam, skill, task_type, title, prompt, answer_key, topic, source_kind, source_url
QUESTIONS = [
    ("IELTS", "writing", "Academic Task 2", "Flexible work and city life", "Some people believe that working from home improves quality of life, while others think it weakens teamwork. Discuss both views and give your own opinion.", None, "work", "ORIGINAL", None),
    ("IELTS", "writing", "Academic Task 2", "Public transport investment", "Some cities spend more on public transport than on roads. To what extent do you agree that this is the best way to reduce traffic problems? Give reasons and examples.", None, "cities", "ORIGINAL", None),
    ("IELTS", "writing", "Academic Task 1", "Library visits table", "The table shows visits to a community library in 2015 and 2025. Adults: 12,000 then 18,000; teenagers: 8,000 then 11,000; children: 10,000 then 9,000. Summarise the main features and make relevant comparisons.", None, "data", "ORIGINAL", None),
    ("IELTS", "speaking", "Part 2 cue card", "A useful skill", "Describe a skill you learned outside school. Say what it was, how you learned it, who helped you, and explain why it is useful now.", None, "skills", "ORIGINAL", None),
    ("IELTS", "speaking", "Part 3 discussion", "Technology and learning", "How has technology changed the way adults learn new skills? Give reasons and examples, and consider a possible disadvantage.", None, "education", "ORIGINAL", None),
    ("IELTS", "reading", "Short-answer practice", "Community garden", "Passage: A neighbourhood garden opened in 2021 on land beside the railway. Volunteers meet every Saturday morning. The project grows herbs and vegetables, and a local school uses the site for science lessons. Question: On which day do volunteers meet?", "saturday", "community", "ORIGINAL", None),
    ("IELTS", "listening", "Transcript-based demo", "Workshop time change", "DEMO TRANSCRIPT (no audio): The photography workshop was planned for eleven, but the instructor moved it to two in the afternoon. Question: At what time is the workshop now?", "two", "events", "ORIGINAL", None),
    ("IELTS", "listening", "Official public samples", "IELTS official Listening sample tasks", None, None, "official", "OFFICIAL_LINK", ACADEMIC_SAMPLES),
    ("IELTS", "reading", "Official public samples", "IELTS official Academic Reading sample tasks", None, None, "official", "OFFICIAL_LINK", ACADEMIC_SAMPLES),
    ("IELTS", "writing", "Official public samples", "IELTS official Academic Writing sample tasks", None, None, "official", "OFFICIAL_LINK", ACADEMIC_SAMPLES),
    ("IELTS", "speaking", "Official public samples", "IELTS official Speaking sample tasks", None, None, "official", "OFFICIAL_LINK", ACADEMIC_SAMPLES),
    ("IELTS", "reading", "Official public samples", "IELTS General Training Reading samples", None, None, "official", "OFFICIAL_LINK", GENERAL_SAMPLES),
    ("IELTS", "writing", "Official public samples", "IELTS General Training Writing samples", None, None, "official", "OFFICIAL_LINK", GENERAL_SAMPLES),
    ("IELTS", "reading", "Official familiarisation", "British Council computer test familiarisation", None, None, "official", "OFFICIAL_LINK", FAMILIARISATION),
]
