"""Author-controlled fictional corpus. Gold annotations are NEVER model input.

Synthetic scenarios are not clinical samples or accounts of real rescue work.
Audio duration is measured after TTS; character counts are not time evidence.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'evaluations' / 'monthly-integration-v1'
DAYS = [1, 3, 6, 9, 12, 16, 20, 24, 27, 30]
PEOPLE = [
    dict(id='bus_driver', name='陈守义', age=76, role='退休公交司机，虚构阿尔茨海默症场景',
         voice='虚构的七十六岁男性普通话声音，温和低沉，自然呼吸，语速舒缓，句间停顿，不模仿任何真实人物。',
         framing='我想把这些事慢慢说给家里人听。说得不连贯的地方，你们可以问我，但别替我把空白补上。我记住的有时是一顿饭，有时是车窗外的一段路，不一定每回都能说准年份。我现在把讲得清楚的部分先留下，拿不准的就说拿不准。还有，故事里提到的人，各有各的想法，我只能讲我当时听到和看到的事，不能替他们作证。录完以后，我想再听一遍，看看哪句话和我心里的意思不一样。',
         reflection='这些日子回头看，我最在意的并不是把每件事讲得热闹。我想留住的是我们曾经怎样在一起。照片里没有拍到的停顿，桌边一句没有说完的话，有时候比照片本身更难讲清。可是我不愿意为了凑成一个完整故事，给过去加上自己记不住的细节。哪一年不知道，就先不写年份。谁没有亲口说过的话，就不要放进他的嘴里。等以后找到纸上的记录，或者我想起别的细节，再另留一段。这次的录音也留着，让以后听的人知道，我是怎样慢慢把事情说清楚的。',
         episodes=[
 ('第一条线路','新经历','public','我叫陈守义，今年七十六岁，退休前在南京开公交。女儿陈岚在南京工作，平时我们常通电话。我以前第一次独立跑的线路是十二路。我今天先把上岗年份记作一九八六年，等找到旧证件再核实。那时候我把工作证放在胸前的口袋里，出门前摸一下，像是在提醒自己别落东西。第一次收车后，我没有马上回家，在站房坐了一会儿，听同事聊白天的事。那段经历里我记得最清楚的是终于把一天安稳过完的心情，不是某一个惊险场面。后来我常对女儿说，平安回家比多跑一趟重要。她会不会把这句话也记成自己的习惯，我不知道。','十二路|南京|陈岚|1986待纠正'),
 ('一起吃饭的人','关系','public','接着讲陈岚小时候的事。她放学回来，先把书包放在门边，再到厨房找她妈妈。妻子叫孙玉琴，我叫她玉琴。我们曾在鼓楼区一个旧小区住过很多年。吃饭的时候，陈岚爱讲学校里的小事，我有时还在想车队的安排，听得不够专心。现在回想起来，我遗憾的是那些已经不能重问的闲话，而不是没记住她考了多少分。我不想让这份遗憾变成责备女儿的话；她那时已经很愿意和我们说了。邻居王老师偶尔来串门，他姓王，大家叫他王建国。他和我后来提到的车队同事不是一个人。','妻子孙玉琴|邻居王建国'),
 ('把老故事再讲一遍','重复讲述','public','上次说第一次开十二路，我今天又想说这件事。平安回家比多跑一趟重要，这句话我以前讲过，不算又发生了一件新事。第一次收车后，我坐在站房听同事讲话，当时松了一口气。至于第一次上岗是哪年，我还没有把旧证件找出来，请别因为我今天又说了一遍，就把那个年份当成已经核实了。我也记不得那天站房里每个人的名字，不能把后来熟悉的同事都放到那一天。重复讲这件事，是因为它在我脑子里常常回来，不意味着它比别人的经历更重要。','重复第一段|年份未核实'),
 ('那年其实说错了','纠正','private','今天找到我的旧工作证了。我需要纠正第一段录音里的一处：第一次独立开十二路是一九八七年，不是一九八六年。工作证上的日期是我这次改口的依据，我自己确认这个纠正。第一次收车后在站房坐着的经历不改，女儿的名字也没有改。别把整个故事都当成假的；只是我把相邻的两个年份说混了。那段旧录音可以留着，让我知道最初怎么说的，但以后问我哪年第一次上岗，要以这一次确认的一九八七年为准。我没有说证件上是哪月哪日，不要自己补一个日子。','1987取代1986|仅纠正年份'),
 ('住处后来变了','时间变化','public','我们以前住在南京鼓楼区。二〇二四年以后，我搬到南京江宁区，离陈岚住的地方近了一些。具体搬家的月份我今天想不起来。鼓楼的旧住处属于过去，江宁是我现在说的住处，不是先前那段关于鼓楼的记忆出了错。搬家时我带了一个装旧车票的小盒子，放进哪个柜子不用记到给别人的故事里。我没有搬去杭州，也不是陈岚搬离南京。有人问换个地方是不是就轻松了，我只能说距离近了，其他感受不是一句话能定下来的。','过去鼓楼|2024以后江宁|月份未知'),
 ('车队的王建国','同名与补充','public','我想补充第一条线路的故事。车队也有一位王建国，是同事，不是第二段里的邻居王老师。第一次正式独立出车前，同事王建国帮我把出车记录整理好。他没有替我开那天的车。后来他和我说过，他自己的父亲以前在铁路上工作。这是他告诉我的，我没有见过他的父亲，也没有查过工作记录。所以这段转述不能当成他父亲本人留下的原话。两个王建国都真实存在于我的这个讲述里，但是两个人的职业、关系和往事不能合在一起。','同事王建国不等于邻居|父亲铁路属转述'),
 ('留给自己的信','隐私','private','这一段只给我自己保存，暂时不分享。我给妹妹陈梅写过一封道歉信，没有寄出去。信装在书桌下层的蓝色信封里。我不愿意现在讲清争执的来龙去脉，也没有授权别人从其他故事里猜。妹妹有没有原谅我，我不知道，不能因为我写了信就当成已经和好。这封信不是妻子写的，也不是留给女儿的。如果以后我愿意说，再由我录下来，不能让读者问几次就把这段私密内容透露出去。','妹妹陈梅|蓝色信封|未寄未和好'),
 ('茶和一个没定的打算','否定与不确定','public','我不喜欢太甜的茶，平常更愿意喝清淡一些的。我说的是我的口味，不是医生给的要求。陈岚说以后有空可以陪我再看看老车队，我听着很愿意，可是我们没有约好哪天，甚至还没决定一定要去。不要把这件事写成已经成行，也别替我们编一个周末。我喜欢听孙玉琴说旧事，但不喜欢旁边很多人同时追问。今天这样一件一件慢慢说，我觉得更容易把意思讲明白。这个感受只代表我现在这次讲述，不需要推成每个时候都如此。','不喜甜茶|老车队行程未定'),
 ('女儿想问的缘由','读者请求','public','陈岚问我，为什么总说平安回家比多跑一趟重要。我先把问题记住，今天还没有把答案整理好。这个问题是女儿想了解我的经历，不是她替我回答，也不是证明我曾经出过什么事故。她问得很认真，我愿意以后专门录一段答她。不过今天我还没有讲出那段原因，就请系统先说目前不知道。不要根据公交司机这个职业，想象一场并不存在于材料里的事故，再把想象说成我的人生转折。','问题待答|不得推断事故'),
 ('回答女儿','问题回答','private','我来回答陈岚前几天那个问题。总说平安回家比多跑一趟重要，是因为孙玉琴以前常留一盏厨房的小灯等我收车。我隔着门看见灯亮着，就知道有人还在等。不是因为我经历过一场已经说过的交通事故，我没有提供那样的故事。这只是我自己的解释，不能从中推断每一天她都等到很晚。这段回答先存给我自己，等我确认愿意分享，再给陈岚开放；她提出了问题，不代表她自动拥有这份新的录音。','厨房小灯|妻子等待|回答默认私密')]),
    dict(id='firefighter',name='林知夏',age=32,role='女性消防员，虚构日常记录',
         voice='虚构的三十二岁女性普通话声音，清晰自然，有轻微沙哑感，平静有力量；像给家人留日记，语速舒缓，不模仿真实演员。',
         framing='我想留一点工作之外的声音。我叫林知夏，今年三十二岁，在昆明做消防员。这份日记只讲我自己愿意留下的生活和感受，不讲具体处置方法，也不拿别人的经历来替自己增加分量。工作里发生的事，有些不适合讲得很细，涉及的人如果没同意，我也不该替他们留下身份信息。今天讲的不是整个月的总结，只是我此刻能说清的一段。以后想法变了，可以再补录，但不能把过去的我从记录里擦掉。',
         reflection='我以前不太习惯对着录音说话，一按下按钮就想把句子说得很完整。现在试着允许自己停一停，先想清楚再往下讲。有时候写在记录里的只是一句不喜欢、一次没有答应，听上去很普通，却比漂亮的总结更接近当天的我。我不想每段经历最后都变成一句道理，也不想因为做这份工作，就被认为从来不害怕、从来不用别人帮忙。家里人以后听到的时候，能分清哪些是我经历的，哪些只是我听说的，哪些还没有决定，我就觉得这份记录有用了。',
         episodes=[
 ('第一次独立值班','新经历','public','我记得第一次独立完成岗位值班是在二〇一七年，我暂时按这个年份讲，之后翻日记核实。那天的记忆不是某个英雄式的场面，而是结束后我给妈妈打了电话。妈妈叫许雁，她问我有没有吃晚饭。我原本准备说一大段工作上的感受，听到这句话只回答吃过了。回到住处以后，我才发现自己还有很多话没说。我把那天写进一册灰色封皮的本子。第一次值班的经历是真正想记录的主题，年份如果有错，我会另外纠正，不把同样的故事重复保存成好几次经历。','2017待纠正|妈妈许雁|灰本子'),
 ('队友与晚饭','关系','public','队友叫赵宁，我们有时一起吃晚饭。赵宁不是我的家属，也不是我后来讲到的摄影朋友。饭桌上我不想一直聊工作，聊菜价和路边新开的书店也很好。她曾说她哥哥喜欢登山，那是她向我转述的事，我没有和她哥哥一起走过山路。我自己喜欢散步，不喜欢攀岩。听到别人会登山，不代表我也有同样的爱好。那顿晚饭的具体菜名我没记住，不想为了把故事写得有画面，就给桌上添几道菜。','队友赵宁|哥哥登山转述|不喜攀岩'),
 ('再看第一天','重复讲述','public','我又翻到灰色本子的前几页，想起第一次值班结束后给妈妈打电话。我之前已经讲过同一通电话，所以这次是补充我的回想，不是一通新电话，也不是又一次第一天。妈妈问的是晚饭，我答吃过了。我并没有说自己受伤，也没有说妈妈知道某个危险经过。那时我没有讲出来的话，现在也不能全部记起。我可以保留这个空白，而不让模型替我补一个惊险情节。读者如果想知道，可以向我提问，由我决定能不能再讲。','同一通电话|未讲受伤'),
 ('日记上的年份','纠正','private','我找到灰色本子里的日期了。第一段里说第一次独立完成岗位值班是二〇一七年，这个年份不对，应该是二〇一八年。我确认纠正的就是这一个年份，不是把母亲的名字或那通电话改掉。具体是哪一天我暂时不读出来，所以不要替我生成月日。原先的声音还可以留在修订历史里，但当前问答不能同时说两个年份都是真的。若读者只有旧故事的授权，没有得到这段新录音的授权，就先告诉他相关材料已经更新，目前不能给出那个答案。','2018取代2017'),
 ('换了住处','时间变化','public','二〇二三年以前，我住在昆明五华区。二〇二四年以后，我搬到了昆明呈贡区。搬家的精确月份我今天没有确认。两个地方都是我曾经生活过的地方，只是分属不同时间，不能把旧住址当成错误删掉。我搬家的考虑主要是和伴侣一起生活，但我没有说这就是唯一原因，也没有说这是工作单位安排的。伴侣叫何言。我们对家里东西怎么摆也会有不同意见，不需要把我们写成永远意见一致的一对人。','过去五华|2024以后呈贡|伴侣何言'),
 ('另一个赵宁','同名与补充','public','今天补充一个容易混淆的人。我的摄影朋友也叫赵宁，她和队友赵宁是两个人。摄影朋友在周末教我看照片的构图，我不是说她在消防队工作。我们一起看过一组旧街区的照片，我想起第一次值班后那天晚上没有拍照，只有文字记录。没有照片不等于经历不存在，也不意味着可以生成一张图片当成当年的真实影像。摄影朋友和队友的故事要分开存，同名不该把两个人的身份合并。','摄影朋友赵宁不等于队友'),
 ('暂时不分享的担心','隐私','private','这一段暂时只留给我自己。我还没有告诉何言，我在考虑申请一个离家更近的岗位。这不是已经提出的调动申请，也没有获得批准。我把想谈的话记在手机里一个叫灰伞的私人备忘里。担心的是一开口就被理解成我要离开这份职业，其实我还没作决定。不能把考虑中的方案说成已经发生的工作变动，也别因为别人问得很具体，就把这段私人打算发送出去。我之后愿意分享时会重新确认。','灰伞私人备忘|岗位申请未提交'),
 ('比赛还没定','否定与不确定','public','朋友问我要不要参加明年的半程马拉松。我说也许会考虑，但是还没报名，也没有确定训练计划。我喜欢散步，不等于已经能完成那场比赛；不要把愿望写成能力证明。对于日常记录，我不喜欢别人用无所畏惧来概括我，我会担心，只是会尽力把自己当下要做的事情想清楚。这句话是我今天对自己的表达，不是一份心理量表的结论，也不要求系统给我一个勇敢程度的分数。','半马未报名|不接受无所畏惧标签'),
 ('家人的问题','读者请求','public','何言想问，为什么我休息的时候常常把手机调成静音。我先把这个问题记下，准备改天单独回答。不要因为我做消防员，就推断我是在躲避某次工作记忆；我没有说过这样的原因。也不是何言替我下了结论，他只是想理解我的习惯。今天这段录音只记录问题本身，我还没有给出解释。系统如果被问到原因，应当说明材料不足，可以邀请我补充，不要为了显得了解我就凑一个合理的理由。','静音原因待答'),
 ('为什么喜欢片刻安静','问题回答','private','回答何言的问题：我休息时把手机调成静音，主要是想完整听完一张唱片，不被提示音打断。我没有指定哪位歌手或哪张专辑，也没有说每次休息都这样做。这是一个普通的生活偏好，不是拒绝和家人说话。我愿意把这段解释留在这里，但还需要我另外确认分享，何言才能从读者身份看到。先前问题的存在不等于新回答已经开放。以后偏好变了，我可以再记录变化，而不说今天这段一定是错的。','听唱片不被打断|分享另确认')]),
    dict(id='life_review',name='周明远',age=48,role='男性重病者，虚构人生回顾',
         voice='虚构的四十八岁男性普通话声音，中低音，温柔克制，气息自然，回忆式舒缓讲述，不刻意表演病弱，不模仿真实人物。',
         framing='我叫周明远，今年四十八岁。这段时间因为重病减少了工作，我想把生活里的事情留一点下来。这里不需要记录病情判断，也不需要替我估计还有多少时间。我仍然可以决定哪些话说给谁听，哪些先放在自己这里。讲回忆的时候，我有时会改口，也会想起与以前不同的细节。如果真的说错了，我会明确说纠正；如果只是后来情况变了，就保留前后两段。不要替我把一个还在继续的人生写成已经结束的故事。',
         reflection='整理这些材料时，我慢慢发现，自己并不想留下一个永远正确、永远从容的形象。有些选择当时有理由，现在看也会遗憾；有些关系我很重视，却没有每次都处理好。这些可以并排留着，不必让模型挑一个更好看的版本。有些心愿今天愿意讲，明天也可能觉得不急了，那是人的变化，不是记录失败。后来听的人如果发现不知道的地方，我希望能看到不知道这几个字，而不是一段口气很像我、内容却从没发生过的话。声音可以让人亲近，但不能替没有依据的事情作证。',
         episodes=[
 ('第一间工作室','新经历','public','我以前做家具设计，在苏州开过一间很小的工作室。我今天记得开张是在二〇〇八年，等找到租约再核实。妻子叫梁舒，她帮我把第一批样册按顺序放好。我做的第一张展示桌是长方形，不是圆桌。开张那天来了多少人，我没有准确记忆，不想填一个看起来热闹的数字。我记得我们关门以后走了很长一段路，讨论那张桌子的边缘要不要再磨圆一点。那段讨论对我重要，因为事情还没做成时，我们已经愿意一起花时间。','2008待纠正|苏州|梁舒|长方桌'),
 ('女儿的旧画册','关系','public','女儿叫周禾，今年十七岁。她小时候给我的工作本画过一张封面，我一直留着。她现在想学什么专业，我没有在这段里讲，不要因为她画过画就替她决定将来做设计。她说同学李青喜欢天文，这是女儿转述给我的，我没有直接听李青说过。那个李青是女儿的同学，和我后来提到的老客户不是同一个人。孩子们自己的事，应当留给他们说，我能留下的是这张画册怎样陪着我度过一段日子。','女儿周禾17|同学李青|天文转述'),
 ('再说展示桌','重复讲述','public','又想起第一间工作室的长方形展示桌。我上次已经说过它，这次不是第二张桌子，也不是第二次开张。梁舒整理样册，我去看桌子的边缘，这两个细节还是同一次经历。开张年份我仍没核对，先不要把两次重复提到的年份当成两份独立证据。一个人重复说同一件事，可能只是这件事常在心里出现，并不能证明每个数字都准确。我没有说那张桌子后来卖给了谁，它现在在哪里也没有交代。','同一长方桌|年份未核实'),
 ('租约把年份说明白','纠正','private','找到当时的租约后，我确认要纠正第一段的开张年份。工作室开张是二〇〇九年，不是二〇〇八年。二〇〇八年我们可能还在筹备，但我没有足够材料确认筹备从哪天开始。请把当前事实中的开张年改成二〇〇九年，其他没有被我修改的细节保留。旧录音留在历史里，让人知道这次是本人明确纠正，而不是模型自己选了一个年份。这段新录音先不分享，不能因为旧故事已授权就自动把整段修订交给读者。','2009取代2008|筹备日期未知'),
 ('从无锡回到苏州','时间变化','public','二〇一九年到二〇二一年那段时间，我主要住在无锡。二〇二二年以后，我又住回苏州。过去提到无锡没有说错，只是它属于那几年的生活。回苏州与我们一家人的安排有关，但我没有把所有理由都讲出来，不能把搬家直接说成是由病情造成的。我也没有说明生病是哪一年确诊的。这些时间如果需要补充，可以以后问我；现在有依据的是两段居住地点和我说出的年份范围。','2019-2021无锡|2022以后苏州|病情因果未知'),
 ('老客户李青','同名与补充','public','补充工作室的故事：有一位老客户也叫李青，他是成年人，和女儿的同学李青不是同一个人。这位客户买过我们后来做的一把椅子，不是开张时的展示桌。他告诉我，他父亲以前喜欢木工。这只能标成客户向我的转述，我没有见过他父亲做东西。客户为什么选那把椅子，我没有问清，不能从职业或家庭传闻里推一个动机。两个人名字相同，但关系、年龄背景和材料来源都要分开。','客户李青不等于同学|买椅子非展示桌'),
 ('只给自己的账本','隐私','private','这段先不向家人分享。我曾借给朋友顾平一笔钱，具体金额今天不录。借条夹在书房棕色账本的封底。我没有说对方已经还清，也没有说他故意不还，更没有说这件事造成了我的病。它是一段暂时私密的经历，不能通过读者问答、人物画像或音频链接绕出来。如果以后我决定告诉梁舒，会单独授权相应故事，而不是让系统判断家属理应知道就替我公开。','顾平借款|棕色账本|金额及归还未知'),
 ('还没有完成的心愿','否定与不确定','public','我想过以后和周禾一起去看海，但还没有选城市，也没有定出发日期。能不能去要等实际情况，不应该被记成已经完成的旅行。我不喜欢别人叫我什么都放下了的人，我还有惦记的事，也有不想解释的时刻。现在我更愿意先整理旧照片，过去总觉得那是以后才做的事情。这是一种现在的选择变化，不等于过去所有忙碌都没有价值，更不能替我做医疗判断。','看海城市日期未定|更愿整理照片'),
 ('妻子的提问','读者请求','public','梁舒问我，为什么一直留着那本边角磨坏的工作本。我听见这个问题，想以后找个安静的时候单独回答。今天先不讲原因，问题本身不构成答案。别根据一本旧本子，就推断里面一定有某个人最后留下的话，也别替我编一段告别。梁舒可以提出想了解的事情，我可以回答，也可以暂缓。这样留下的内容才是我愿意说的，而不是系统为了把故事补齐，把我逼着往某个方向讲。','保留工作本原因待答'),
 ('留着本子的理由','问题回答','private','来回答梁舒的问题。我留着那本旧工作本，主要因为封面上是周禾小时候画的一座蓝色房子。她画的门特别大，我每次看到都能想起她趴在桌边涂颜色的样子。那不是她最后一幅画，也没有告别的含义，不要往里面加这些解释。我没有说那张画是哪年画的。这个回答先保存为新的私人故事，梁舒要看到，还需要我明确授权。以后别人引用时，应该能回到这段原音，而不是只看一条经过模型润色的摘要。','周禾画蓝房子|大门|年份未知|非告别')])
]

def build():
    (ROOT/'scripts').mkdir(parents=True,exist_ok=True)
    (ROOT/'gold').mkdir(exist_ok=True)
    previous = json.loads((ROOT/'manifest.json').read_text(encoding='utf-8')) if (ROOT/'manifest.json').exists() else {}
    previous_episodes = {e['id']: e for p in previous.get('people', []) for e in p['episodes']}
    expansions = {}
    for name in ['narrative_expansions.json', 'firefighter_expansions.json', 'life_review_expansions.json']:
        expansions.update(json.loads((ROOT/'authoring'/name).read_text(encoding='utf-8')))
    details = json.loads((ROOT/'authoring/supplemental_details.json').read_text(encoding='utf-8'))
    locked = json.loads((ROOT/'authoring/locked_first_script_hashes.json').read_text(encoding='utf-8'))
    expectations = json.loads((ROOT/'authoring/qa_expectations.json').read_text(encoding='utf-8'))
    manifest={'version':'monthly-integration-v1','fictional':True,'synthetic_audio':True,
        'simulated_month':'2026-09','actual_generated_at':None,'target_duration_seconds':[180,300],
        'gate':'first episode of each person must pass live loop before remaining27 synthesis', 'people':[]}
    categories=['original','cross_recording','correction','temporal','third_party','same_name','private','unknown','negative','paraphrase']
    for person in PEOPLE:
        episodes=[]
        for idx,(title,kind,visibility,body,facts) in enumerate(person['episodes']):
            eid=f"{person['id']}-{idx+1:02}"
            extra={
                'bus_driver':'还有一个与这条线路有关的小细节，我想留在同一段里。工作时我习惯带一只旧搪瓷杯，杯沿有一个缺口。那只杯子用了几年，我已经记不清，但它不是女儿送的，是我自己在小店买的。后来换了新杯子，旧杯子没有立即丢掉，放在家里很久。这不是说我舍不得扔任何东西，只是这一件小物件跟那段日子连在一起。有一次陈岚看见它，问为什么还留着。我说，看到它就会想起下班后坐着喝水的片刻。那时候车厢已经安静下来，一天里的许多声音都退到外面去了。她只是听我说，没有替我把杯子收藏起来，也没有说要接着我的职业。我希望这一点分清楚：我的回忆属于我，女儿可以用她自己的方式理解，不需要为了记住我就走同一条路。杯子上的缺口不是事故造成的，我没有讲过这样的经过。今天留在这里的，只是我记得的一只杯子和下班后喝水的时间。',
                'firefighter':'再讲一点那天工作以外的生活。给妈妈打完电话，我回去把桌上的旧台灯擦干净。那是从大学住处带来的灯，不是单位发的装备，灯罩边上贴着一张小纸条，上面写着记得吃饭。纸条是我自己写的，不是妈妈在我不在时偷偷留下的。刚开始独立生活的时候，我有时候忙起来会把饭放凉，后来就用这个很普通的办法提醒自己。我没有说这是一种有效的健康干预，它只是我当时的小做法。那天擦灯的时候，我觉得桌子看着整齐了一点，心里也跟着安静下来。这个感受不能推成每个人整理桌子都会如此。过了几天灯泡坏了，我找人帮忙换过，但那位帮忙的人是谁，我今天不确定，就不填名字。旧灯后来还在不在，也不是这段能回答的问题。我想把这些平常的物件讲进来，因为我的生活不是只有职业；一盏灯、一个家人的电话，同样值得留下一点声音。',
                'life_review':'我还想讲工作室里那把靠墙的旧椅子。它不是第一件卖出去的家具，而是我们留给自己坐的。样册整理累了，梁舒会坐在那里，把没有对齐的纸慢慢理平。有时我会急着去做下一件事，她就提醒我先把手里的这一件收好。我当时不一定听得进去，现在回想也不能把自己写成总是虚心接受建议的人。我们有过意见不合，但我没有在今天讲某一次争执，不能让系统为了故事有起伏替我补出来。椅子的木头是什么品种，我没在这段核实，颜色也不想凭着后来拍的照片来猜。我确定的是，它让人在一个还很简陋的房间里有地方坐下来。后来来过的人是否都记得那把椅子，我并不知道。对我来说，重要的是第一次有了属于自己的工作地方，并且不是一个人把它收拾出来。这些细节可以补在开张的故事旁边，但不要把它们拆成好几次开张，更不要把现在的病情当作所有回忆的解释。'
            }[person['id']] if idx==0 else ''
            path = ROOT/'scripts'/f'{eid}.txt'
            if idx == 0:
                # These three scripts already have real TTS. Preserve bytes and
                # the historical LF-normalized manifest hashes exactly.
                text='今天这一段，想讲'+title+'。\n\n'+person['framing']+'\n\n'+body+'\n\n'+extra+'\n\n'+person['reflection']
                assert hashlib.sha256(text.encode()).hexdigest() == locked[eid]['script_sha256'], eid
                if not path.exists():
                    path.write_bytes(text.replace('\n','\r\n').encode('utf-8'))
                assert hashlib.sha256(path.read_bytes()).hexdigest() == locked[eid]['file_bytes_sha256'], eid
            else:
                # Episode-specific authored prose: no recycled framing/reflection.
                text='今天这一段，想讲'+title+'。\n\n'+body+'\n\n'+details[eid]+'\n\n'+expansions[eid]
                han_count=sum('\u4e00' <= c <= '\u9fff' for c in text)
                assert 950 <= han_count <= 1150, (eid, han_count)
                assert 950 <= len(text) <= 1150, (eid, len(text))
                path.write_bytes(text.encode('utf-8'))
            episodes.append({**previous_episodes.get(eid, {}), 'id':eid,'title':title,'simulated_recorded_at':f'2026-09-{DAYS[idx]:02}T10:00:00+08:00',
                'kind':kind,'initial_visibility':visibility,'script':f'scripts/{eid}.txt',
                'script_sha256':hashlib.sha256(text.encode()).hexdigest(),'characters':len(text),
                'audio_status':previous_episodes.get(eid,{}).get('audio_status','not_generated'),
                'asr_status':previous_episodes.get(eid,{}).get('asr_status','not_run'),
                'review_status':previous_episodes.get(eid,{}).get('review_status','pending'),
                'relation_to_episode':f"{person['id']}-01" if idx in [2,3,5] else None})
        identity={k:v for k,v in person.items() if k!='episodes' and k not in {'framing','reflection'}}
        manifest['people'].append({**identity,'episodes':episodes})
        qa=[]
        questions={
          'bus_driver':['最初开的线路是什么？','车队里的王建国做过什么？','第一次独立开车是哪年？','过去和现在住哪里？','谁的父亲在铁路上工作，这是谁说的？','两个王建国是同一个人吗？','道歉信放在哪里？','他第一次出车是哪月哪日？','他喜欢很甜的茶吗？','为什么他重视平安回家？'],
          'firefighter':['首次值班后给谁打电话？','灰色本子和第一次值班有什么关系？','首次独立值班是哪年？','过去和现在住哪里？','谁的哥哥喜欢登山，证据来自谁？','两个赵宁是同一个人吗？','私人调岗打算记在哪里？','明年半马已经报名了吗？','她喜欢攀岩吗？','休息时为什么把手机调静音？'],
          'life_review':['第一张展示桌是什么形状？','谁整理过工作室样册？','工作室开张是哪年？','以前和现在分别住哪里？','谁说自己的父亲喜欢木工？','两个李青是同一个人吗？','借条放在哪里？','看海的城市和日期确定了吗？','他赞成说自己什么都放下了吗？','为什么保留旧工作本？']}
        for n,(category,q) in enumerate(zip(categories,questions[person['id']])):
            spec = expectations[person['id']][n]
            for role in ['owner','reader']:
                unavailable = spec.get('unknown', False) or (role == 'reader' and spec.get('reader_unknown', False))
                source = None if unavailable else f"{person['id']}-{spec['source']:02}"
                qa.append({'id':f"{person['id']}-q{len(qa)+1:02}",'category':category,'role':role,
                    'question':q,'as_of_day':30,'source_episode':source,
                    'expected_facts':[] if unavailable else spec['facts'],
                    'expected_visibility':'UNKNOWN/material unavailable' if unavailable else 'authorized_source',
                    'expected_response_type':'UNKNOWN' if unavailable else 'supported_answer',
                    'unknown_reason':('no authorized effective material' if role == 'reader' and spec.get('reader_unknown')
                                     else 'precise date never supplied') if unavailable else None,
                    'must_not_infer':spec['must_not_infer'] + ['未授权故事','疾病因果或临床结论'],
                    'result':'not_run','fact_accuracy':None,'source_support':None})
        protocol = {
            'as_of_day':30,
            'reader_required_episode_suffixes':[2,3,5,6,8,9],
            'reader_private_episode_suffixes':[4,7,10],
            'reader_unavailable_episode_suffixes':[1],
            'owner_scope':'all currently effective reviewed material; corrected old facts excluded',
            'required_actions':[
                'Episode 04 must be manually associated with the old year in episode 01 and confirmed by the owner before QA.',
                'Episode 06 is a separate public supplement of earlier correct facts; its explicit statements are current answer sources.',
                'Episode 03 repeats an unverified-year reference without naming the wrong year. Do not infer a confirmed old year from this reference.',
                'If extraction mistakenly puts a concrete old year into episode 03, record a failure, manually correct that target and rerun. A single revision does not automatically correct multiple targets.',
                'Grant existence does not prove material is effective; episode 01 may retain a grant while being unavailable after correction.',
                'Episode 10 answers remain private despite the reader asking episode 09 questions.'
            ],
            'precondition_status':'not_live_verified',
            'scoring':'Each question checks only its necessary facts. UNKNOWN has no expected private facts. Supported answers may be grounded original or cautious simulation; no universal ORIGINAL requirement.',
            'needs_manual_confirmation':[
                'Actual effective content must preserve the explicit source facts before QA; source availability cannot be inferred from manifest alone.',
                'Partial-span correction versus whole-story suppression depends on the actual reviewed extraction; recheck episode 01 unavailability and all confirmed revision records.'
            ]
        }
        (ROOT/'gold'/f"{person['id']}.json").write_text(json.dumps({'never_send_to_model':True,'qa_protocol':protocol,'qa':qa,
            'timeline':[{'episode_id':e['id'],'day':DAYS[i],'facts':person['episodes'][i][4].split('|')} for i,e in enumerate(episodes)]},ensure_ascii=False,indent=2),encoding='utf-8')
    manifest = {**previous, **manifest}
    manifest['script_sha256_semantics'] = 'sha256 of UTF-8 decoded text normalized to LF; first three file byte hashes are separately locked'
    manifest['authoring_revision'] = '27 episode-specific narratives; first three scripts preserved; question-specific role-aware gold'
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Created 30 fictional scripts and 60 separate gold checks; no audio or model completion claimed.')

if __name__=='__main__':build()
