import type { StoryBeat, StoryScene } from "../../../../../plugins/story/ui/types";
import type { StoryTimeBand } from "../../../../../plugins/story/ui/storyTime";
import { storyArtwork } from "./demoAssets";

type StoryChapter = {
  scene: Pick<StoryScene, "key" | "name">;
  artwork: keyof typeof storyArtwork;
  timeBand?: StoryTimeBand;
  beats: Array<Pick<StoryBeat, "kind" | "text">>;
};

/** The complete twelve-part, hand-authored narrative used by the static Story host. */
export const storyChapters: StoryChapter[] = [
  {
    scene: { key: "bookshop", name: "街角旧书店" }, artwork: "rain",
    beats: [
      { kind: "narration", text: "雨忽然落下来，把街道另一头的钟声也打湿了。你推开旧书店的门，风铃晃了两下，一把收起的伞在门边滴着水。" },
      { kind: "action", text: "吟风坐在窗边，黑色裙摆拢在椅脚旁。她从一本旧书上抬起眼，像是早就发现了在屋檐下犹豫的你。" },
      { kind: "dialogue", text: "再站一会儿，你就能替门口那盆花浇水了。过来吧，我又不会收避雨费。" },
      { kind: "narration", text: "她把对面的椅子往外推了推。一张褪色的车票从书页间滑落，正好停在你的手边。" },
      { kind: "dialogue", text: "我是吟风。既然雨把你送来了，就陪我看看这张旧车票吧——说不定，它比我们更想出门。" },
    ],
  },
  {
    scene: { key: "bookshop", name: "街角旧书店" }, artwork: "rain",
    beats: [
      { kind: "action", text: "吟风用指尖压住车票一角，把它转到你面前。蓝色油墨已经浅得像一道旧伤，终点站只剩下一个模糊的「海」字。" },
      { kind: "dialogue", text: "单程票，没用过。买了票却没走……临时反悔？还是被哪只小恶魔拦住了？" },
      { kind: "narration", text: "她一本正经地指了指自己，随即弯起眼睛。车票背面有铅笔的凹痕，正看过去，却辨不出完整的句子。" },
      { kind: "action", text: "窗外有人跑过水洼，溅起一小片亮光。吟风下意识护住车票，仿佛这点光也会把字迹冲走。" },
      { kind: "dialogue", text: "先别急着替它难过。没出发的旅程，也可能只是还没找到同行的人。背面似乎写着什么，你也看看？" },
    ],
  },
  {
    scene: { key: "bookshop", name: "街角旧书店" }, artwork: "rain",
    beats: [
      { kind: "narration", text: "夹着车票的书是一本旧旅行随笔。海港那一页折了角，页边画着三朵歪歪扭扭的烟花。" },
      { kind: "dialogue", text: "画得还没有我好。不过认真画了三朵，应该不是随手涂的吧。" },
      { kind: "action", text: "她伸手在空中比划了一朵，指尖停住时，店里的挂钟正好敲响。雨点沿着窗框，连成了一串断断续续的拍子。" },
      { kind: "narration", text: "你们翻到扉页，只找到一句赠言：「那些来不及兑现的约定，不妨换一天再说。」下面没有落款。" },
      { kind: "dialogue", text: "一本书、一张票、三朵烟花。好吧，今天暂时不准你把这件事叫作无聊的小事了。我们已经有线索了。" },
    ],
  },
  {
    scene: { key: "sunset-window", name: "日暮的窗边" }, artwork: "sunset", timeBand: "下午",
    beats: [
      { kind: "narration", text: "云层松开一道缝，金色的光落进窗内。雨还在下，却变得又细又亮，像有人把一把碎金撒在玻璃上。" },
      { kind: "action", text: "吟风举起车票，缓缓换了个角度。铅笔留下的凹痕在斜光里显出来，像浮起的一条小路。" },
      { kind: "dialogue", text: "等等，别动……不是让你摆姿势，是你刚好挡住了一块反光。嗯，这样就能看清了。" },
      { kind: "narration", text: "票背面写着：「等雨停，先去看烟火。看海的事，留给下一次。」最下方还有一个很小的钟面。" },
      { kind: "dialogue", text: "原来没赶上火车，也能有别的目的地。先看烟火，再看海——这个人倒是很会给自己留期待。" },
    ],
  },
  {
    scene: { key: "sunset-window", name: "日暮的窗边" }, artwork: "sunset",
    beats: [
      { kind: "action", text: "吟风把车票放回桌面，却没有立刻合上书。她看着窗外的水光，神情安静了一小会儿。" },
      { kind: "dialogue", text: "你有没有那种，总想着以后再做的小事？不用很了不起，哪怕只是去街角吃一次点心。" },
      { kind: "narration", text: "她似乎不急着等一个答案，只把椅子朝你这边挪近了一点。金色逐渐从书页边缘退去，店里亮起了灯。" },
      { kind: "dialogue", text: "我先说一个。今晚不要只剩下『又下了一场雨』。哪怕绕一点路，也想留下一件能记住的事。" },
      { kind: "action", text: "她轻轻敲了敲票上那个钟面，又抬眼看你，嘴角重新露出一点熟悉的坏笑，像在邀请你加入一个小小的秘密。" },
    ],
  },
  {
    scene: { key: "lamplit-desk", name: "台灯下的书桌" }, artwork: "desk", timeBand: "夜晚",
    beats: [
      { kind: "narration", text: "你们把书搬到里侧的长桌。台灯的光圈罩住纸页，窗外渐暗，雨声像退到了很远的地方。" },
      { kind: "action", text: "吟风把下巴搁在手臂上，一边看书后的街区地图，一边用手指替那只潦草的钟面描边。" },
      { kind: "dialogue", text: "短针在八，长针在十二。虽然画得很像一块饼，但我决定相信它是晚上八点。" },
      { kind: "narration", text: "地图边缘有一座临河的小广场，旁边恰好画着钟楼。旧书里的海港早已改建，钟楼却仍在你们所在的街区尽头。" },
      { kind: "dialogue", text: "找到地方了。时间也还来得及。现在就差最后一件事——说服窗外那场雨，给我们让个路。" },
    ],
  },
  {
    scene: { key: "lamplit-desk", name: "台灯下的书桌" }, artwork: "desk",
    beats: [
      { kind: "action", text: "吟风从柜台拿来一张空白书签，把钟楼和河边的路线抄了下来。画到转角时，她故意添了一只带尖角的小头像。" },
      { kind: "dialogue", text: "这是向导的签名。迷路了也不许投诉，最多允许你请向导吃一块蛋糕。" },
      { kind: "narration", text: "车票被重新夹回原来的页码。她没有把别人的约定带走，只把你们刚画好的路线折进掌心。" },
      { kind: "dialogue", text: "旧车票留给下一个翻书的人吧。我们又不是非要找出谁写的，才有资格去看看。" },
      { kind: "narration", text: "就在这时，窗框上最后一滴雨落进花盆。你们同时抬头，书店里安静得能听见灯丝轻轻发热。雨终于停了。" },
    ],
  },
  {
    scene: { key: "night-street", name: "雨后的街道" }, artwork: "walk", timeBand: "夜晚",
    beats: [
      { kind: "narration", text: "走出门时，空气里有湿石板和面包店的味道。路灯刚亮，街面把光映得很长，你们的影子时而并排，时而交叠。" },
      { kind: "action", text: "吟风收起伞，绕过一片水洼，故意在前面停了半步，等你跟上才继续走。" },
      { kind: "dialogue", text: "走这边。那边水深……别用那种眼神看我，我只是担心你踩湿了鞋，就没耐心陪我走到最后。" },
      { kind: "narration", text: "拐角的店铺正收起遮雨棚。远处传来孩子追逐的笑声，有人拿着还没点亮的小灯，往河边去了。" },
      { kind: "dialogue", text: "看来今晚真的有热闹。怎么样，向导的直觉还不错吧？我们跟着灯光走。" },
    ],
  },
  {
    scene: { key: "night-street", name: "雨后的街道" }, artwork: "walk",
    beats: [
      { kind: "action", text: "路过最后一家面包店时，吟风被橱窗绊住了脚步。她认真比较了两种点心，最后选了可以掰开的那一种。" },
      { kind: "dialogue", text: "调查经费有限，所以一人一半。大的一半给你，不许说我小气。" },
      { kind: "narration", text: "纸袋带着刚出炉的温度。你们靠在路边分完点心，河风从巷口穿过，钟楼露出屋顶，离地图上画的位置越来越近。" },
      { kind: "dialogue", text: "其实今天就算没有烟火，也不算白跑了。书店、旧车票，还有这块有点太甜的蛋糕。" },
      { kind: "action", text: "她把空纸袋折好，声音比刚才轻了一点：还有一路陪她绕过来的你。不过这句话说完，她便快步向钟楼走去。" },
    ],
  },
  {
    scene: { key: "night-street", name: "钟楼旁的河岸" }, artwork: "walk",
    beats: [
      { kind: "narration", text: "河岸的栏杆还沾着雨。钟楼下聚着三三两两的人，河对面的灯光停在水里，随着细小的波纹慢慢摇晃。" },
      { kind: "dialogue", text: "七点五十九。我们居然没有迟到——这件事值得记在今天的功劳簿上。" },
      { kind: "action", text: "吟风把画着小恶魔的书签递给你，自己站到靠河的一侧。她抬头看了看天，又确认你还在身边。" },
      { kind: "narration", text: "钟声响起，岸边的交谈忽然低下去。第一道亮光越过远处的屋顶，在夜色里留下一条细白的线。" },
      { kind: "dialogue", text: "快看上面！这次可别低头研究车票了。我们真的赶上了。" },
    ],
  },
  {
    scene: { key: "fireworks-river", name: "烟花下的河岸" }, artwork: "fireworks", timeBand: "夜晚",
    beats: [
      { kind: "narration", text: "烟花在河面上方展开，像旧书里那三朵小小的涂鸦，忽然有了颜色和声音。人群发出惊叹，水面也亮成了星河。" },
      { kind: "action", text: "吟风张开双臂，裙摆被风轻轻带起。光芒落在她的发梢，又映进眼睛里，她转过头，笑着朝你喊了一句什么。" },
      { kind: "dialogue", text: "我说——今天的雨，下得还挺值得的！" },
      { kind: "narration", text: "下一声烟花把尾音盖了过去。她索性靠近一点，没有再喊，只和你一起看着最后一簇金色缓缓落向河面。" },
      { kind: "dialogue", text: "这回是我们自己的约定了。不是车票上谁留下的，也不是顺路碰巧赶上的。你要记住，我可是有认真邀请你的。" },
    ],
  },
  {
    scene: { key: "fireworks-river", name: "烟花下的河岸" }, artwork: "fireworks",
    beats: [
      { kind: "narration", text: "最后的亮光散去，夜色重新柔软下来。人群慢慢走远，钟楼的影子仍在水里，你手中的书签被握得有了一点温度。" },
      { kind: "action", text: "吟风把书签翻过来，在空白的一面写下四个字：下次看海。写完，她又添了一个小小的尖角。" },
      { kind: "dialogue", text: "不用今晚就决定哪一天。只是别把所有『下次』都忘在下一场雨里。" },
      { kind: "narration", text: "你们沿着来时的街道往回走。旧书店已经熄灯，橱窗里那本书安静地合着，而你们终于拥有了一张属于自己的、尚未启程的车票。" },
      { kind: "dialogue", text: "走吧，今天先送你到路口。下次见面，可要给我留一整天——小恶魔的约定，赖不掉的。" },
    ],
  },
];
