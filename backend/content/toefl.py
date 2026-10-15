"""Original TOEFL iBT (January 2026 format) practice items.

Task types follow the updated test: Complete the Words, Read in Daily Life,
Read an Academic Passage, Listen and Choose a Response, conversations,
announcements, academic talks, Write an Email, Academic Discussion,
Listen and Repeat and Take an Interview.
"""

N, F, M, F2, M2 = "narrator", "female", "male", "female2", "male2"


def line(voice, speaker, text):
    return {"voice": voice, "speaker": speaker, "text": text}


def options(*texts):
    return [{"key": "ABCD"[i], "text": text} for i, text in enumerate(texts)]


LISTENING_RESPONSE = {
    "id": "toefl-listening-response", "kind": "listening", "exam": "TOEFL", "part": 1,
    "title": "Listen and Choose a Response", "topic": "campus life",
    "context": "You will hear a person speak. Choose the best response.",
    "script": [],
    "groups": [{"title": "Questions 1-4", "type": "mcq", "instructions": "Listen to each speaker and choose the best response. Each recording plays once.", "questions": [
        {"n": 1, "clip": [line(M, "Student", "Do you know if the library is open late during exam week?")], "prompt": "Choose the best response.",
         "options": options("Yes, it stays open until midnight.", "I borrowed three books.", "The exam was really difficult.", "No, I don't have a library card."), "answer": "A", "evidence": "Asks about opening hours; only A answers that."},
        {"n": 2, "clip": [line(F, "Classmate", "I missed Tuesday's lecture. Could I borrow your notes?")], "prompt": "Choose the best response.",
         "options": options("The lecture hall is on the second floor.", "Sure, I'll send you a copy tonight.", "Tuesday is usually busy.", "I didn't enjoy the lecture."), "answer": "B", "evidence": "A request to borrow notes; B accepts it."},
        {"n": 3, "clip": [line(M2, "Professor", "Your essay is due Friday, but I can give you an extension if you need one.")], "prompt": "Choose the best response.",
         "options": options("I finished reading the book.", "Friday is my favourite day.", "Thanks, a couple more days would really help.", "I'll be in class on Friday."), "answer": "C", "evidence": "An offer of an extension; C accepts it appropriately."},
        {"n": 4, "clip": [line(F2, "Roommate", "Why don't we cook dinner together instead of ordering takeaway again?")], "prompt": "Choose the best response.",
         "options": options("Good idea, I'll pick up some vegetables.", "The takeaway was delivered late.", "I already ate breakfast.", "Dinner is at seven."), "answer": "A", "evidence": "A suggestion; A agrees and adds a related action."},
    ]}],
}

LISTENING_CONVERSATION = {
    "id": "toefl-listening-conversation", "kind": "listening", "exam": "TOEFL", "part": 2,
    "title": "Conversation: room change request", "topic": "campus life",
    "context": "Listen to a conversation between a student and a housing office employee.",
    "script": [
        line(N, "Narrator", "Listen to a conversation between a student and an employee in the university housing office."),
        line(F, "Student", "Hi, I was hoping to ask about changing rooms. I'm in Maple Hall right now."),
        line(M, "Employee", "Sure. Is there a problem with your current room?"),
        line(F, "Student", "Well, it's not the room exactly. Maple Hall is right next to the sports stadium, and there are evening games three or four times a week. I have an early chemistry lab, so I really need to sleep before eleven."),
        line(M, "Employee", "I see. Unfortunately, we don't usually allow room changes until the second week of the semester. We want everyone to settle in first."),
        line(F, "Student", "Oh. Is there anything I can do in the meantime?"),
        line(M, "Employee", "You can fill out a request form today, and we'll put you on the waiting list. Students who apply early get priority. Also, Cedar House is the quietest building on campus, so I'd suggest listing that as your first choice."),
        line(F, "Student", "That's great. Does it cost more?"),
        line(M, "Employee", "Cedar House rooms are slightly smaller, so actually they're about fifty dollars cheaper per semester."),
        line(F, "Student", "Even better. I'll fill out the form now."),
    ],
    "groups": [{"title": "Questions 5-8", "type": "mcq", "instructions": "Choose the best answer.", "questions": [
        {"n": 5, "prompt": "Why does the student go to the housing office?", "options": options("To complain about her roommate", "To ask about moving to a different room", "To pay her housing fee", "To find a job on campus"), "answer": "B", "evidence": "I was hoping to ask about changing rooms."},
        {"n": 6, "prompt": "What is the problem with Maple Hall?", "options": options("It is far from the chemistry building.", "It is too expensive.", "It is noisy because of sports events.", "The rooms are too small."), "answer": "C", "evidence": "next to the sports stadium, and there are evening games"},
        {"n": 7, "prompt": "What does the employee suggest?", "options": options("Waiting until next semester", "Applying early and choosing Cedar House", "Moving off campus", "Talking to the chemistry professor"), "answer": "B", "evidence": "Students who apply early get priority ... Cedar House is the quietest"},
        {"n": 8, "prompt": "What is true about Cedar House rooms?", "options": options("They are larger.", "They cost less.", "They are reserved for graduate students.", "They are next to the stadium."), "answer": "B", "evidence": "about fifty dollars cheaper per semester"},
    ]}],
}

LISTENING_ANNOUNCEMENT = {
    "id": "toefl-listening-announcement", "kind": "listening", "exam": "TOEFL", "part": 3,
    "title": "Announcement: science building closure", "topic": "campus life",
    "context": "Listen to an announcement made at the start of a class.",
    "script": [
        line(N, "Narrator", "Listen to an announcement made by a professor at the beginning of class."),
        line(M2, "Professor", "Before we start, a quick announcement. The science building will be closed next Monday and Tuesday so that the electrical system can be upgraded. That means our Tuesday lab session will move to the engineering building, room two-fourteen. Please bring your safety goggles, because the engineering labs don't provide them. Also, the deadline for your lab report is being pushed back from Wednesday to Friday to give you the extra time you'd have had in the lab."),
    ],
    "groups": [{"title": "Questions 9-10", "type": "mcq", "instructions": "Choose the best answer.", "questions": [
        {"n": 9, "prompt": "Why will the science building be closed?", "options": options("For a safety inspection", "To upgrade the electrical system", "Because of a holiday", "For a conference"), "answer": "B", "evidence": "so that the electrical system can be upgraded"},
        {"n": 10, "prompt": "What must students bring to the lab session?", "options": options("Their lab reports", "Their textbooks", "Safety goggles", "A laptop"), "answer": "C", "evidence": "Please bring your safety goggles"},
    ]}],
}

LISTENING_TALK = {
    "id": "toefl-listening-talk", "kind": "listening", "exam": "TOEFL", "part": 4,
    "title": "Academic talk: the Mpemba effect", "topic": "physics",
    "context": "Listen to part of a talk in a physics class.",
    "script": [
        line(N, "Narrator", "Listen to part of a talk in a physics class."),
        line(F, "Professor", "Today I want to discuss a puzzle that has been debated for decades: can hot water freeze faster than cold water? It sounds impossible, but people have reported it since ancient times. Aristotle mentioned it, in fact."),
        line(F, "Professor", "The modern name, the Mpemba effect, comes from Erasto Mpemba, a secondary school student in Tanzania. In the nineteen sixties, he noticed that his hot ice cream mixture froze before his classmates' cooler mixtures. His teacher didn't believe him, but Mpemba persisted, and eventually he co-authored a paper with a physics professor."),
        line(F, "Professor", "So what could explain it? One idea is evaporation: hot water loses more mass to evaporation, so there's less water left to freeze. Another is that hot water contains less dissolved gas. A third explanation involves convection currents that move heat out of the water more efficiently."),
        line(F, "Professor", "Here's the problem, though. When scientists try to reproduce the effect under carefully controlled conditions, the results are inconsistent. Small differences, such as the shape of the container or the exact position of the thermometer, can change the outcome. So many physicists now think the effect is real in some situations but depends heavily on the experimental setup, rather than being a universal law."),
    ],
    "groups": [{"title": "Questions 11-14", "type": "mcq", "instructions": "Choose the best answer.", "questions": [
        {"n": 11, "prompt": "What is the talk mainly about?", "options": options("How ice cream is made", "Whether hot water can freeze faster than cold water", "The life of Aristotle", "Problems with school science teaching"), "answer": "B", "evidence": "can hot water freeze faster than cold water?"},
        {"n": 12, "prompt": "Why does the professor mention Erasto Mpemba?", "options": options("To explain the origin of the effect's name", "To criticise his teacher", "To describe a failed experiment", "To show that the effect is a myth"), "answer": "A", "evidence": "The modern name, the Mpemba effect, comes from Erasto Mpemba"},
        {"n": 13, "prompt": "Which is NOT given as a possible explanation?", "options": options("Evaporation", "Dissolved gases", "Convection currents", "Magnetic fields"), "answer": "D", "evidence": "Evaporation, dissolved gas and convection are mentioned; magnetism is not."},
        {"n": 14, "prompt": "What do many physicists now believe?", "options": options("The effect never happens.", "The effect is a universal law.", "The effect depends on experimental conditions.", "The effect only occurs with ice cream."), "answer": "C", "evidence": "depends heavily on the experimental setup"},
    ]}],
}

READING_CWORDS = {
    "id": "toefl-reading-cwords", "kind": "reading", "exam": "TOEFL", "part": 1,
    "title": "Complete the Words", "topic": "biology", "minutes": 4,
    "passage": [{"label": "", "text": "Fill in the missing letters to complete the words in the paragraph."}],
    "groups": [{"title": "Questions 1-8", "type": "cwords", "instructions": "Fill in the missing letters in the paragraph.",
                "text": "Migratory birds travel thousands of kilometres each year. Sci{{1}} have long wondered h{{2}} they find their way. Rec{{3}} studies suggest th{{4}} many species use the ear{{5}} magnetic field, wh{{6}} others rely on the posi{{7}} of the stars. Young birds of{{8}} learn routes by following older ones.",
                "questions": [
                    {"n": 1, "prefix": "Sci", "answer": "scientists", "accepts": ["scientists"]},
                    {"n": 2, "prefix": "h", "answer": "how", "accepts": ["how"]},
                    {"n": 3, "prefix": "Rec", "answer": "recent", "accepts": ["recent"]},
                    {"n": 4, "prefix": "th", "answer": "that", "accepts": ["that"]},
                    {"n": 5, "prefix": "ear", "answer": "earth's", "accepts": ["earth's", "earths"]},
                    {"n": 6, "prefix": "wh", "answer": "while", "accepts": ["while", "whilst", "whereas"]},
                    {"n": 7, "prefix": "posi", "answer": "position", "accepts": ["position", "positions"]},
                    {"n": 8, "prefix": "of", "answer": "often", "accepts": ["often"]},
                ]}],
}

READING_DAILY = {
    "id": "toefl-reading-daily", "kind": "reading", "exam": "TOEFL", "part": 2,
    "title": "Read in Daily Life: gym notice", "topic": "campus life", "minutes": 5,
    "passage": [{"label": "", "text": "CAMPUS RECREATION CENTRE - SUMMER HOURS\n\nFrom June 1 to August 20, the Recreation Centre will open from 7:00 a.m. to 8:00 p.m. on weekdays and from 10:00 a.m. to 4:00 p.m. on Saturdays. The centre will be closed on Sundays.\n\nThe swimming pool will be closed from June 1 to June 14 for cleaning. Summer members may use the outdoor tennis courts free of charge during this period.\n\nSummer membership costs $45 for students and $70 for staff. Bring your university ID to the front desk to register. Lockers can be rented for $10 per month."}],
    "groups": [{"title": "Questions 9-11", "type": "mcq", "instructions": "Choose the best answer.", "questions": [
        {"n": 9, "prompt": "When is the centre closed during the summer?", "options": options("Saturdays", "Sundays", "Weekday evenings", "All of June"), "answer": "B", "evidence": "The centre will be closed on Sundays."},
        {"n": 10, "prompt": "What can members do while the pool is being cleaned?", "options": options("Rent a locker for free", "Use the tennis courts at no cost", "Get a membership refund", "Swim at a different pool"), "answer": "B", "evidence": "may use the outdoor tennis courts free of charge"},
        {"n": 11, "prompt": "What must students bring to register?", "options": options("$70", "A locker key", "Their university ID", "A tennis racket"), "answer": "C", "evidence": "Bring your university ID to the front desk to register."},
    ]}],
}

READING_ACADEMIC = {
    "id": "toefl-reading-academic", "kind": "reading", "exam": "TOEFL", "part": 3,
    "title": "Read an Academic Passage: coral reef recovery", "topic": "ecology", "minutes": 8,
    "passage": [
        {"label": "", "text": "Coral reefs cover less than one percent of the ocean floor, yet they support roughly a quarter of all marine species. Reefs are built by tiny animals called polyps, which live in partnership with microscopic algae. The algae provide the polyps with food through photosynthesis, and in return they receive shelter and nutrients."},
        {"label": "", "text": "When water temperatures rise even one or two degrees above normal for several weeks, this partnership breaks down. The polyps expel the algae, and because the algae give coral its colour, the reef turns white, a process known as bleaching. Bleached coral is not dead, but it is starving, and if temperatures do not return to normal, it will eventually die."},
        {"label": "", "text": "Some reefs, however, recover more quickly than others. Researchers have found that reefs with large populations of plant-eating fish recover faster, because the fish prevent seaweed from covering the surface where new coral larvae need to settle. Scientists are also experimenting with breeding heat-tolerant corals in laboratories and transplanting them onto damaged reefs, although critics warn that this approach is expensive and can only be applied on a small scale."},
    ],
    "groups": [{"title": "Questions 12-15", "type": "mcq", "instructions": "Choose the best answer.", "questions": [
        {"n": 12, "prompt": "According to paragraph 1, what do the algae provide for the polyps?", "options": options("Shelter", "Food", "Protection from fish", "Colourful shells"), "answer": "B", "evidence": "The algae provide the polyps with food through photosynthesis"},
        {"n": 13, "prompt": "The word 'expel' in paragraph 2 is closest in meaning to", "options": options("feed", "protect", "force out", "attract"), "answer": "C", "evidence": "The polyps expel the algae"},
        {"n": 14, "prompt": "Why do reefs with many plant-eating fish recover faster?", "options": options("The fish eat harmful coral larvae.", "The fish keep seaweed from covering the reef.", "The fish lower the water temperature.", "The fish bring new algae to the reef."), "answer": "B", "evidence": "the fish prevent seaweed from covering the surface"},
        {"n": 15, "prompt": "What concern do critics raise about heat-tolerant coral?", "options": options("It is not really heat tolerant.", "It harms local fish.", "It is costly and limited in scale.", "It grows too slowly in laboratories."), "answer": "C", "evidence": "this approach is expensive and can only be applied on a small scale"},
    ]}],
}

WRITING = [
    {"id": "toefl-writing-email", "kind": "writing", "exam": "TOEFL", "task": "email", "title": "Email to a club organiser", "topic": "campus life",
     "prompt": "You recently joined a university photography club, but the weekly meetings now clash with one of your classes.\n\nWrite an email to the club organiser, Ms. Lin. In your email, do the following:\n- Explain the problem.\n- Suggest a possible solution.\n- Ask about something else related to the club.\n\nWrite as much as you can and in complete sentences.",
     "min_words": 100, "minutes": 7},
    {"id": "toefl-writing-discussion", "kind": "writing", "exam": "TOEFL", "task": "discussion", "title": "Academic discussion: city planning", "topic": "urban studies",
     "prompt": "Your professor is teaching a class on urban studies. Write a post responding to the professor's question. In your response, you should express and support your opinion and make a contribution to the discussion in your own words.\n\nDr. Ramirez: Many cities are turning car lanes into bicycle lanes and pedestrian areas. Is this a good use of public space? Why or why not?\n\nKenji: I think it's positive. When I visited Copenhagen, the streets were quieter and people seemed healthier because they cycled everywhere.\n\nAmara: I'm not so sure. In cities with cold winters or long distances, many people can't realistically cycle, and removing car lanes just makes traffic worse.",
     "min_words": 100, "minutes": 10},
]

SPEAKING = [{
    "id": "toefl-speaking-campus", "kind": "speaking", "exam": "TOEFL", "title": "Listen and Repeat + Take an Interview", "topic": "campus life",
    "repeat": [
        {"text": "Welcome to the campus visitor centre."},
        {"text": "Maps of the university are available at the front desk."},
        {"text": "The guided tour leaves from the main entrance every hour."},
        {"text": "Please keep your visitor badge with you at all times."},
        {"text": "The library and the student union are both open to visitors until six."},
        {"text": "If you would like to attend a lecture, please ask a member of staff first."},
        {"text": "We hope you enjoy your visit and look forward to seeing you again soon."},
    ],
    "interview": {"scenario": "A researcher is interviewing students about how they use technology for studying.", "questions": [
        "Thanks for joining me. To start, what technology do you use most often when you study?",
        "Some students say studying with music helps them concentrate, while others find it distracting. What is your experience?",
        "Many universities now record lectures and put them online. Do you think students should still be required to attend lectures in person? Why or why not?",
        "Finally, some educators believe artificial intelligence tools will make students less independent thinkers. Do you agree or disagree? Please explain.",
    ]},
    "answer_seconds": 45,
}]

LISTENING = [LISTENING_RESPONSE, LISTENING_CONVERSATION, LISTENING_ANNOUNCEMENT, LISTENING_TALK]
READING = [READING_CWORDS, READING_DAILY, READING_ACADEMIC]
