"""Original IELTS Writing tasks (with chart data) and full Speaking test scripts."""

WRITING = [
    {"id": "ielts-writing-t1-library", "kind": "writing", "exam": "IELTS", "task": "task1", "title": "Library visits by age group", "topic": "data",
     "prompt": "The chart below shows the number of visits to a community library by three age groups in 2015 and 2025. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.",
     "chart": {"type": "bar", "title": "Library visits by age group", "unit": "visits", "categories": ["Adults", "Teenagers", "Children"],
               "series": [{"name": "2015", "values": [12000, 8000, 10000]}, {"name": "2025", "values": [18000, 11000, 9000]}]},
     "min_words": 150, "minutes": 20},
    {"id": "ielts-writing-t1-commute", "kind": "writing", "exam": "IELTS", "task": "task1", "title": "How employees commute", "topic": "transport",
     "prompt": "The chart below shows the percentage of employees in one city who travelled to work by car, train and bicycle in 2010 and 2025. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.",
     "chart": {"type": "bar", "title": "Commuting methods (% of employees)", "unit": "%", "categories": ["Car", "Train", "Bicycle"],
               "series": [{"name": "2010", "values": [60, 25, 15]}, {"name": "2025", "values": [45, 35, 20]}]},
     "min_words": 150, "minutes": 20},
    {"id": "ielts-writing-t1-energy", "kind": "writing", "exam": "IELTS", "task": "task1", "title": "Electricity from renewable sources", "topic": "energy",
     "prompt": "The graph below shows the proportion of electricity generated from renewable sources in three countries between 2000 and 2025. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.",
     "chart": {"type": "line", "title": "Renewable share of electricity (%)", "unit": "%", "categories": ["2000", "2005", "2010", "2015", "2020", "2025"],
               "series": [{"name": "Country A", "values": [8, 10, 15, 24, 35, 48]}, {"name": "Country B", "values": [20, 21, 22, 25, 27, 30]}, {"name": "Country C", "values": [2, 3, 6, 12, 25, 41]}]},
     "min_words": 150, "minutes": 20},
    {"id": "ielts-writing-t1-spending", "kind": "writing", "exam": "IELTS", "task": "task1", "title": "Household spending", "topic": "economy",
     "prompt": "The pie charts below show how an average household in one country spent its income in 1995 and 2025. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.",
     "chart": {"type": "pie", "title": "Household spending (%)", "unit": "%", "categories": ["Housing", "Food", "Transport", "Leisure", "Other"],
               "series": [{"name": "1995", "values": [24, 31, 14, 11, 20]}, {"name": "2025", "values": [36, 19, 15, 17, 13]}]},
     "min_words": 150, "minutes": 20},
    {"id": "ielts-writing-t2-remote", "kind": "writing", "exam": "IELTS", "task": "task2", "title": "Working from home", "topic": "work",
     "prompt": "Some people believe that working from home improves quality of life, while others think it weakens teamwork and career development. Discuss both these views and give your own opinion.\n\nGive reasons for your answer and include any relevant examples from your own knowledge or experience.",
     "min_words": 250, "minutes": 40},
    {"id": "ielts-writing-t2-transport", "kind": "writing", "exam": "IELTS", "task": "task2", "title": "Investing in public transport", "topic": "cities",
     "prompt": "Some cities spend more money on public transport than on building new roads. To what extent do you agree or disagree that this is the best way to reduce traffic problems?\n\nGive reasons for your answer and include any relevant examples from your own knowledge or experience.",
     "min_words": 250, "minutes": 40},
    {"id": "ielts-writing-t2-university", "kind": "writing", "exam": "IELTS", "task": "task2", "title": "The purpose of university", "topic": "education",
     "prompt": "Some people believe universities should focus on preparing students for specific jobs. Others believe university education should develop broader knowledge and thinking skills. Discuss both views and give your own opinion.\n\nGive reasons for your answer and include any relevant examples from your own knowledge or experience.",
     "min_words": 250, "minutes": 40},
    {"id": "ielts-writing-t2-green", "kind": "writing", "exam": "IELTS", "task": "task2", "title": "Disappearing green spaces", "topic": "environment",
     "prompt": "In many cities, parks and open spaces are being replaced by new housing and offices. What problems does this cause? What measures could be taken to address these problems?\n\nGive reasons for your answer and include any relevant examples from your own knowledge or experience.",
     "min_words": 250, "minutes": 40},
    {"id": "ielts-writing-t2-ai", "kind": "writing", "exam": "IELTS", "task": "task2", "title": "Artificial intelligence in schools", "topic": "technology",
     "prompt": "Artificial intelligence tools can now write essays and solve problems for students. Some people think schools should ban them, while others believe students should learn to use them. Discuss both views and give your own opinion.\n\nGive reasons for your answer and include any relevant examples from your own knowledge or experience.",
     "min_words": 250, "minutes": 40},
    {"id": "ielts-writing-t2-tourism", "kind": "writing", "exam": "IELTS", "task": "task2", "title": "Mass tourism", "topic": "travel",
     "prompt": "International tourism has brought enormous numbers of visitors to some historic cities. Do the advantages of this development outweigh the disadvantages?\n\nGive reasons for your answer and include any relevant examples from your own knowledge or experience.",
     "min_words": 250, "minutes": 40},
]

PART1_TOPICS = [
    {"topic": "your hometown", "questions": ["Where is your hometown?", "What do you like most about it?", "Has your hometown changed much in recent years?", "Would you like to live there in the future?"]},
    {"topic": "work or studies", "questions": ["Do you work or are you a student?", "Why did you choose that job or subject?", "What do you find most challenging about it?", "What would you like to do in the future?"]},
    {"topic": "reading", "questions": ["Do you enjoy reading?", "What kinds of things do you usually read?", "Did you read a lot when you were a child?", "Do you prefer paper books or e-books?"]},
    {"topic": "music", "questions": ["What kind of music do you like?", "When do you usually listen to music?", "Have you ever learned to play an instrument?", "Is music important in your culture?"]},
    {"topic": "the weather", "questions": ["What is the weather usually like where you live?", "What is your favourite kind of weather?", "Does the weather affect your mood?", "Do you check the weather forecast often?"]},
    {"topic": "cooking", "questions": ["Do you like cooking?", "Who usually cooks in your family?", "What is a dish you can make well?", "Do you think children should learn to cook at school?"]},
    {"topic": "weekends", "questions": ["What do you usually do at weekends?", "Do you prefer busy or relaxing weekends?", "What did you do last weekend?", "Are weekends different now from when you were younger?"]},
    {"topic": "mobile phones", "questions": ["How often do you use your mobile phone?", "What do you mainly use it for?", "Could you live without a phone for a week?", "Do you think people use their phones too much?"]},
]

PART2_CARDS = [
    {"topic": "a skill", "cue": "Describe a skill you learned outside school or university.", "bullets": ["what the skill is", "when and how you learned it", "who helped you", "and explain why this skill is useful to you"],
     "closing": "Do you think you will continue to develop this skill?",
     "part3": {"theme": "learning skills", "questions": ["What skills do you think young people should learn today?", "Is it better to learn a skill from a teacher or by yourself online?", "Why do some adults find it hard to learn new things?", "How might the skills employers want change in the next twenty years?"]}},
    {"topic": "a journey", "cue": "Describe a journey that you remember well.", "bullets": ["where you went", "how you travelled", "who you were with", "and explain why you remember this journey"],
     "closing": "Would you like to make that journey again?",
     "part3": {"theme": "travel and transport", "questions": ["Why do people enjoy travelling to new places?", "How has tourism changed in your country in recent years?", "Should governments limit the number of tourists in popular places?", "Do you think people will travel less in the future because of the environment?"]}},
    {"topic": "a helpful person", "cue": "Describe a person who has helped you in an important way.", "bullets": ["who this person is", "how you know them", "what they did to help you", "and explain how you felt about their help"],
     "closing": "Have you thanked this person?",
     "part3": {"theme": "helping others", "questions": ["Why do some people enjoy helping others?", "Should schools require students to do volunteer work?", "Are people less willing to help strangers than in the past?", "What role should governments play in helping people in need?"]}},
    {"topic": "a place to relax", "cue": "Describe a place where you like to relax.", "bullets": ["where it is", "how often you go there", "what you do there", "and explain why it helps you relax"],
     "closing": "Do other people know about this place?",
     "part3": {"theme": "stress and lifestyle", "questions": ["Why do many people find it difficult to relax nowadays?", "Is it the responsibility of employers to reduce stress at work?", "How do people in cities and the countryside relax differently?", "Do you think technology helps people relax or makes them more stressed?"]}},
    {"topic": "a piece of technology", "cue": "Describe a piece of technology you find useful.", "bullets": ["what it is", "when you got it", "how often you use it", "and explain why you find it useful"],
     "closing": "Is there anything you dislike about it?",
     "part3": {"theme": "technology and society", "questions": ["How has technology changed the way people communicate?", "Should older people be encouraged to learn new technology?", "Do you think technology makes people less creative?", "What are the risks of relying too much on technology?"]}},
    {"topic": "a decision", "cue": "Describe an important decision you made.", "bullets": ["what the decision was", "when you made it", "how you made it", "and explain why it was important"],
     "closing": "Do you think it was the right decision?",
     "part3": {"theme": "decision making", "questions": ["What important decisions do young people have to make?", "Should parents make decisions for their teenage children?", "Why do some people find it hard to make decisions?", "Is it better to make decisions quickly or slowly?"]}},
]


def speaking_test(seed: int) -> dict:
    """Assemble one full Speaking test: two Part 1 topics, a cue card and its Part 3 discussion."""
    first = PART1_TOPICS[seed % len(PART1_TOPICS)]
    second = PART1_TOPICS[(seed + 3) % len(PART1_TOPICS)]
    card = PART2_CARDS[seed % len(PART2_CARDS)]
    return {"id": f"ielts-speaking-{seed % len(PART2_CARDS)}", "kind": "speaking", "exam": "IELTS", "title": f"Speaking test: {card['topic']}",
            "topic": card["topic"],
            "part1": [first, {"topic": second["topic"], "questions": second["questions"][:3]}],
            "part2": {k: card[k] for k in ("topic", "cue", "bullets", "closing")},
            "part3": card["part3"], "prep_seconds": 60, "talk_seconds": 120}


SPEAKING_TESTS = [speaking_test(index) for index in range(len(PART2_CARDS))]
