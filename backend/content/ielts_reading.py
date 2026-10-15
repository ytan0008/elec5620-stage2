"""Original IELTS Academic Reading passages with authentic task types.

Passages are written for this project; question types mirror the test:
TRUE/FALSE/NOT GIVEN, matching headings, multiple choice, YES/NO/NOT GIVEN and
summary/sentence completion.
"""

TFNG = [{"key": "TRUE", "text": "TRUE"}, {"key": "FALSE", "text": "FALSE"}, {"key": "NOT GIVEN", "text": "NOT GIVEN"}]
YNNG = [{"key": "YES", "text": "YES"}, {"key": "NO", "text": "NO"}, {"key": "NOT GIVEN", "text": "NOT GIVEN"}]

PASSAGE_1 = {
    "id": "ielts-reading-1", "kind": "reading", "exam": "IELTS", "part": 1,
    "title": "The return of the city beekeeper", "topic": "nature", "minutes": 20,
    "passage": [
        {"label": "", "text": "For most of the twentieth century, keeping bees was regarded as a rural pastime, practised by farmers and a handful of enthusiasts in country villages. Over the last two decades, however, beehives have appeared on the roofs of hotels, offices and even railway stations in cities such as London, Paris and New York. In Paris alone, the number of registered hives rose from around 300 in 2010 to more than 2,000 a decade later."},
        {"label": "", "text": "Several factors explain this growth. Media coverage of the decline in bee populations, often linked to the use of agricultural pesticides, persuaded many city dwellers that they could help by providing a safe home for bees. Companies also discovered that a rooftop hive was an attractive way to demonstrate environmental responsibility, and some began to give jars of 'office honey' to clients as gifts."},
        {"label": "", "text": "Surprisingly, urban bees often produce more honey than their rural relatives. Cities contain an enormous variety of flowering plants in parks, gardens and along roadsides, and these flower at different times, providing food from early spring to late autumn. In contrast, the countryside is frequently dominated by a single crop, which flowers for only a few weeks. Cities are also slightly warmer, which allows bees to forage for longer each year."},
        {"label": "", "text": "Not everyone welcomes the trend. Ecologists point out that honeybees are only one of hundreds of bee species, and that most wild bees live alone rather than in hives. A study in London found that the number of hives had grown faster than the supply of flowers, raising concern that honeybees may be competing with wild species for limited food. Some researchers therefore argue that planting flowers would do more for bees than installing new hives."},
        {"label": "", "text": "Beekeeping associations have responded by encouraging new members to complete a training course before buying a colony, and several cities now require hives to be registered. Experienced keepers stress that a hive needs regular inspection, particularly in early summer, when a colony may divide and a large group of bees, known as a swarm, leaves to find a new home. In a crowded city, a swarm on a busy street can cause alarm, although swarming bees are rarely aggressive."},
    ],
    "groups": [
        {"title": "Questions 1-6", "type": "tfng", "instructions": "Do the following statements agree with the information given in the passage? Choose TRUE if the statement agrees with the information, FALSE if the statement contradicts the information, NOT GIVEN if there is no information on this.", "options": TFNG, "questions": [
            {"n": 1, "prompt": "Beekeeping in the twentieth century was mainly a rural activity.", "answer": "TRUE", "evidence": "keeping bees was regarded as a rural pastime"},
            {"n": 2, "prompt": "The number of hives in Paris fell after 2010.", "answer": "FALSE", "evidence": "rose from around 300 in 2010 to more than 2,000"},
            {"n": 3, "prompt": "Some companies give honey from their hives to customers.", "answer": "TRUE", "evidence": "some began to give jars of 'office honey' to clients as gifts"},
            {"n": 4, "prompt": "Urban honey has a stronger flavour than rural honey.", "answer": "NOT GIVEN", "evidence": "The passage compares quantity, not flavour."},
            {"n": 5, "prompt": "Most wild bee species live in large colonies.", "answer": "FALSE", "evidence": "most wild bees live alone rather than in hives"},
            {"n": 6, "prompt": "Swarming bees usually attack people nearby.", "answer": "FALSE", "evidence": "swarming bees are rarely aggressive"},
        ]},
        {"title": "Questions 7-13", "type": "completion", "instructions": "Complete the sentences below. Choose ONE WORD ONLY from the passage for each answer.", "questions": [
            {"n": 7, "prompt": "Many people believe the fall in bee numbers is caused by ___ used on farms.", "answer": "pesticides", "accepts": ["pesticides", "pesticide"], "evidence": "often linked to the use of agricultural pesticides"},
            {"n": 8, "prompt": "Companies saw hives as a way to show environmental ___.", "answer": "responsibility", "accepts": ["responsibility"], "evidence": "demonstrate environmental responsibility"},
            {"n": 9, "prompt": "Rural areas are often dominated by one ___.", "answer": "crop", "accepts": ["crop"], "evidence": "dominated by a single crop"},
            {"n": 10, "prompt": "Higher temperatures in cities let bees ___ for longer.", "answer": "forage", "accepts": ["forage"], "evidence": "allows bees to forage for longer each year"},
            {"n": 11, "prompt": "In London, hives increased faster than the supply of ___.", "answer": "flowers", "accepts": ["flowers", "flower"], "evidence": "had grown faster than the supply of flowers"},
            {"n": 12, "prompt": "Several cities now require hives to be ___.", "answer": "registered", "accepts": ["registered"], "evidence": "several cities now require hives to be registered"},
            {"n": 13, "prompt": "A group of bees leaving to find a new home is called a ___.", "answer": "swarm", "accepts": ["swarm"], "evidence": "known as a swarm"},
        ]},
    ],
}

PASSAGE_2 = {
    "id": "ielts-reading-2", "kind": "reading", "exam": "IELTS", "part": 2,
    "title": "Paper: a two-thousand-year journey", "topic": "history", "minutes": 20,
    "passage": [
        {"label": "A", "text": "Paper is so common today that it is easy to forget it was once a precious invention. According to official Chinese records, a court official named Cai Lun presented a method for making paper to the emperor in 105 CE. Archaeological finds, however, show that rough paper existed in China at least two centuries earlier. Cai Lun's real contribution seems to have been to improve and standardise the process, using tree bark, hemp and old fishing nets."},
        {"label": "B", "text": "For several centuries the technique remained in East Asia. It reached Korea and Japan by the seventh century, where craftsmen developed fine papers from the inner bark of the mulberry tree. The westward spread was slower. A popular story claims that Chinese papermakers captured at the Battle of Talas in 751 taught their skills in Samarkand, but historians now believe the knowledge had already travelled along trade routes before then."},
        {"label": "C", "text": "What is clear is that Baghdad became a great centre of papermaking by the end of the eighth century. Paper was cheaper than parchment, which was made from animal skin, and it was harder to alter, because ink soaked into the fibres. For this reason, government offices insisted on paper for official documents. The availability of cheap writing material contributed to a flowering of scholarship, and libraries in the city held hundreds of thousands of books."},
        {"label": "D", "text": "Europe was a late adopter. The first European paper mills appeared in Spain and Italy in the twelfth and thirteenth centuries. Italian mills introduced important innovations, including water-powered hammers to beat the fibres and the watermark, a faint design pressed into the sheet to identify its maker. Even so, many Europeans distrusted paper at first: in 1231 the Holy Roman Emperor declared that documents written on paper had no legal value."},
        {"label": "E", "text": "Demand exploded after the arrival of the printing press in the mid-fifteenth century. Paper was still made from cotton and linen rags, and by the eighteenth century there was a serious shortage. Papermakers experimented with straw, cabbage stalks and even wasp nests, after a French scientist observed that wasps build their nests from chewed wood."},
        {"label": "F", "text": "The solution finally came in the 1840s, when inventors in Germany and Canada independently developed methods for producing pulp from wood. Wood was abundant and cheap, and newspapers and books became affordable for ordinary people. The change had a cost, however. Early wood-pulp paper contained acids that make it turn yellow and brittle, and libraries today spend large sums trying to preserve books printed between 1850 and 1950."},
    ],
    "groups": [
        {"title": "Questions 14-19", "type": "matching", "instructions": "The passage has six paragraphs, A-F. Choose the correct heading for each paragraph from the list of headings below.",
         "options": [
            {"key": "i", "text": "A material that resisted forgery"},
            {"key": "ii", "text": "The search for alternatives to rags"},
            {"key": "iii", "text": "An inventor who refined an existing practice"},
            {"key": "iv", "text": "Cheap material with a hidden weakness"},
            {"key": "v", "text": "Doubtful accounts of how the knowledge moved"},
            {"key": "vi", "text": "The decline of paper in the digital age"},
            {"key": "vii", "text": "Technical progress and early suspicion"},
            {"key": "viii", "text": "Why emperors banned paper"},
         ],
         "questions": [
            {"n": 14, "prompt": "Paragraph A", "answer": "iii", "evidence": "Cai Lun's real contribution seems to have been to improve and standardise the process"},
            {"n": 15, "prompt": "Paragraph B", "answer": "v", "evidence": "historians now believe the knowledge had already travelled along trade routes"},
            {"n": 16, "prompt": "Paragraph C", "answer": "i", "evidence": "it was harder to alter, because ink soaked into the fibres"},
            {"n": 17, "prompt": "Paragraph D", "answer": "vii", "evidence": "Italian mills introduced important innovations ... many Europeans distrusted paper"},
            {"n": 18, "prompt": "Paragraph E", "answer": "ii", "evidence": "Papermakers experimented with straw, cabbage stalks and even wasp nests"},
            {"n": 19, "prompt": "Paragraph F", "answer": "iv", "evidence": "Early wood-pulp paper contained acids that make it turn yellow and brittle"},
         ]},
        {"title": "Questions 20-23", "type": "mcq", "instructions": "Choose the correct letter, A, B, C or D.", "questions": [
            {"n": 20, "prompt": "What does the writer say about Cai Lun?", "options": [{"key": "A", "text": "He was the first person to make paper."}, {"key": "B", "text": "His method was kept secret by the emperor."}, {"key": "C", "text": "Paper existed before his work."}, {"key": "D", "text": "He used only tree bark."}], "answer": "C", "evidence": "rough paper existed in China at least two centuries earlier"},
            {"n": 21, "prompt": "Mulberry bark was used for fine paper in", "options": [{"key": "A", "text": "Korea and Japan."}, {"key": "B", "text": "Samarkand."}, {"key": "C", "text": "Baghdad."}, {"key": "D", "text": "Spain."}], "answer": "A", "evidence": "It reached Korea and Japan ... fine papers from the inner bark of the mulberry tree"},
            {"n": 22, "prompt": "The watermark was used to", "options": [{"key": "A", "text": "strengthen the paper."}, {"key": "B", "text": "show who produced the paper."}, {"key": "C", "text": "make documents legal."}, {"key": "D", "text": "reduce the use of rags."}], "answer": "B", "evidence": "a faint design pressed into the sheet to identify its maker"},
            {"n": 23, "prompt": "Why do libraries spend money on books from 1850-1950?", "options": [{"key": "A", "text": "They are rare and valuable."}, {"key": "B", "text": "They were printed with poor ink."}, {"key": "C", "text": "Their paper deteriorates."}, {"key": "D", "text": "They were made from rags."}], "answer": "C", "evidence": "acids that make it turn yellow and brittle"},
        ]},
        {"title": "Questions 24-26", "type": "completion", "instructions": "Complete the summary. Choose ONE WORD ONLY from the passage for each answer.", "questions": [
            {"n": 24, "prompt": "Before paper, official documents in the Middle East were often written on ___, made from animal skin.", "answer": "parchment", "accepts": ["parchment"], "evidence": "Paper was cheaper than parchment, which was made from animal skin"},
            {"n": 25, "prompt": "Italian mills used hammers powered by ___.", "answer": "water", "accepts": ["water"], "evidence": "water-powered hammers"},
            {"n": 26, "prompt": "A French scientist noticed that ___ make their nests from chewed wood.", "answer": "wasps", "accepts": ["wasps", "wasp"], "evidence": "wasps build their nests from chewed wood"},
        ]},
    ],
}

PASSAGE_3 = {
    "id": "ielts-reading-3", "kind": "reading", "exam": "IELTS", "part": 3,
    "title": "The surprising value of boredom", "topic": "psychology", "minutes": 20,
    "passage": [
        {"label": "", "text": "Boredom has a poor reputation. It is associated with idleness and wasted time, and modern technology seems designed to ensure we never have to experience it: a smartphone offers instant distraction whenever a queue moves slowly or a conversation falters. Yet a growing body of psychological research suggests that boredom is not simply an unpleasant gap between more meaningful experiences. It may, in fact, serve a useful purpose."},
        {"label": "", "text": "Psychologists generally define boredom as the uncomfortable feeling of wanting to be engaged in a satisfying activity but being unable to find one. Crucially, it is different from relaxation, in which a person is content to do nothing. The discomfort, researchers argue, is the point: like hunger or pain, boredom is a signal that something needs to change, prompting us to look for new goals."},
        {"label": "", "text": "This idea was tested in a widely cited experiment by Sandi Mann and Rebekah Cadman. One group of participants spent fifteen minutes copying numbers from a telephone directory, a deliberately dull task, while a control group went straight to the next stage. Both groups were then asked to think of as many uses as possible for a pair of plastic cups. Those who had completed the boring task produced more ideas, and their ideas were judged to be more original. Mann and Cadman concluded that boredom allows the mind to wander, and that daydreaming encourages creative thinking."},
        {"label": "", "text": "Not all researchers accept this interpretation. Critics note that the experiments typically involve small groups of university students, and that the improvements, while statistically significant, are modest. Others point out that chronic boredom, as opposed to brief episodes, is linked to a range of negative outcomes, including overeating and poor performance at school. The writer Tim Lomas has suggested that the important distinction is not between boredom and its absence, but between boredom that a person can respond to and boredom from which there is no escape, such as in a monotonous job."},
        {"label": "", "text": "What, then, are we to make of our constant use of screens? Some psychologists worry that by reaching for a phone at the first sign of boredom, people deprive themselves of the opportunity to reflect, plan and imagine. This does not mean that we should seek out tedium. But it may be worth tolerating a few minutes of it occasionally, if only to see where our thoughts lead."},
    ],
    "groups": [
        {"title": "Questions 27-30", "type": "mcq", "instructions": "Choose the correct letter, A, B, C or D.", "questions": [
            {"n": 27, "prompt": "According to the second paragraph, boredom differs from relaxation because", "options": [{"key": "A", "text": "it lasts for a longer time."}, {"key": "B", "text": "it involves a desire to be occupied."}, {"key": "C", "text": "it is caused by technology."}, {"key": "D", "text": "it only affects active people."}], "answer": "B", "evidence": "wanting to be engaged in a satisfying activity but being unable to find one"},
            {"n": 28, "prompt": "The writer compares boredom to hunger in order to show that it", "options": [{"key": "A", "text": "is a physical condition."}, {"key": "B", "text": "can be dangerous."}, {"key": "C", "text": "warns us that change is needed."}, {"key": "D", "text": "is impossible to ignore."}], "answer": "C", "evidence": "boredom is a signal that something needs to change"},
            {"n": 29, "prompt": "In Mann and Cadman's experiment, participants who did the dull task", "options": [{"key": "A", "text": "gave more creative answers."}, {"key": "B", "text": "finished the second task faster."}, {"key": "C", "text": "copied fewer numbers."}, {"key": "D", "text": "refused to continue."}], "answer": "A", "evidence": "Those who had completed the boring task produced more ideas"},
            {"n": 30, "prompt": "Tim Lomas believes the key question is whether", "options": [{"key": "A", "text": "boredom is brief or long."}, {"key": "B", "text": "people can do something about their boredom."}, {"key": "C", "text": "work is interesting."}, {"key": "D", "text": "screens cause boredom."}], "answer": "B", "evidence": "boredom that a person can respond to and boredom from which there is no escape"},
        ]},
        {"title": "Questions 31-35", "type": "ynng", "instructions": "Do the following statements agree with the claims of the writer? Choose YES if the statement agrees with the claims of the writer, NO if the statement contradicts the claims of the writer, NOT GIVEN if it is impossible to say what the writer thinks about this.", "options": YNNG, "questions": [
            {"n": 31, "prompt": "Boredom may have a positive function.", "answer": "YES", "evidence": "It may, in fact, serve a useful purpose."},
            {"n": 32, "prompt": "The participants in boredom experiments represent the general population well.", "answer": "NO", "evidence": "the experiments typically involve small groups of university students"},
            {"n": 33, "prompt": "Children today are more easily bored than in the past.", "answer": "NOT GIVEN", "evidence": "The passage does not compare generations."},
            {"n": 34, "prompt": "People should deliberately look for dull activities.", "answer": "NO", "evidence": "This does not mean that we should seek out tedium."},
            {"n": 35, "prompt": "Using a phone whenever we are bored may reduce time for reflection.", "answer": "YES", "evidence": "people deprive themselves of the opportunity to reflect, plan and imagine"},
        ]},
        {"title": "Questions 36-40", "type": "completion", "instructions": "Complete the summary below. Choose NO MORE THAN TWO WORDS from the passage for each answer.", "questions": [
            {"n": 36, "prompt": "In the experiment, one group copied numbers from a telephone ___.", "answer": "directory", "accepts": ["directory", "telephone directory"], "evidence": "copying numbers from a telephone directory"},
            {"n": 37, "prompt": "Both groups suggested uses for plastic ___.", "answer": "cups", "accepts": ["cups", "a pair of plastic cups"], "evidence": "a pair of plastic cups"},
            {"n": 38, "prompt": "The researchers believed that ___ encourages creative thinking.", "answer": "daydreaming", "accepts": ["daydreaming", "day dreaming", "day-dreaming"], "evidence": "daydreaming encourages creative thinking"},
            {"n": 39, "prompt": "Critics say the improvements were real but ___.", "answer": "modest", "accepts": ["modest"], "evidence": "while statistically significant, are modest"},
            {"n": 40, "prompt": "Long-term boredom has been linked to overeating and poor performance at ___.", "answer": "school", "accepts": ["school"], "evidence": "overeating and poor performance at school"},
        ]},
    ],
}

PASSAGES = [PASSAGE_1, PASSAGE_2, PASSAGE_3]
FULL_TEST = ["ielts-reading-1", "ielts-reading-2", "ielts-reading-3"]
