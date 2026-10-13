/* Hand-curated fictional demo excerpts. These are not AI extraction results. */
(function (root) {
  const categories = [
    {id:'warmth', label:'温暖', color:'#B27736', meaning:'被照顾的日常'},
    {id:'care', label:'牵挂', color:'#A56677', meaning:'留在心上的人'},
    {id:'growth', label:'成长', color:'#657EA8', meaning:'慢慢明白的事'},
    {id:'kindness', label:'善意', color:'#578578', meaning:'人与人之间的小事'},
    {id:'quiet', label:'沉静', color:'#8879AA', meaning:'愿意停留的片刻'}
  ];
  const episodes = {
    E01:{title:'雨夜，留着一盏灯',year:'2016',image:'library',duration:88.32,alt:'雨夜的社区图书馆，柜台边有一把伞，窗边亮着柔和的灯。'},
    E02:{title:'那碗已经凉了的汤',year:'2017',image:'supper',duration:76.48,alt:'冬夜靠窗的餐桌，两把椅子，一碗汤静静留在暖光里。'},
    E03:{title:'等汤自己变甜',year:'2018',image:'kitchen',duration:78.72,alt:'熟悉的厨房，萝卜汤冒着热气，旧食谱放在窗边。'}
  };
  const raw = [
    ['warmth','E03','妈妈的小本子','这是妈妈的话，不是我发明的做菜道理。','旧食谱留下的，不只有做菜的方法。'],
    ['warmth','E01','替我盖好的饭菜','她已经把饭菜盖好了，还问我要不要再热一遍。','回到家，有人留着一顿饭。'],
    ['warmth','E03','不一样，也喜欢','后来小雨来吃饭，说味道跟外婆做的不完全一样，但她喜欢。','味道可以不同，心意仍然被接住了。'],
    ['care','E02','一碗凉了的汤','她说没关系，可我看见那碗汤都凉了，心里一下就难受起来。','那碗汤，让等待变得具体。'],
    ['care','E01','理解，也会等待','现在回头看，理解不等于他们不会等我。','后来才读懂，家人的体谅里也有等待。'],
    ['care','E02','写进日历的约定','我开始把和她的约定写在日历上。','把在乎的人，放进日常的安排。'],
    ['growth','E03','终于愿意慢下来','我留下这段记忆，是因为那天我第一次愿意为一锅汤慢下来。','一次很小的改变，也有被记住的理由。'],
    ['growth','E02','早点告诉她','她没有跟我吵，只说下回如果来不了，早点告诉她。','有些约定，是从一次迟到开始认真对待的。'],
    ['growth','E02','停下那句解释','我那晚原想解释同事有多忙，话到一半停住了','这一次，她选择先听懂对方的等待。'],
    ['kindness','E01','借出一把伞','我把柜台后面那把备用伞借给他','下雨的夜晚，一把备用伞有了去处。'],
    ['kindness','E01','一张谢谢的便条','我把便条夹在值班本里放了很久。','小小的回应，也可以留很久。'],
    ['kindness','E01','等他走到街口','等他走到街口，才把卷帘门拉下来。','那个晚上，关门的时间往后挪了一点。'],
    ['quiet','E01','窗边的灯与雨','后来我一直记得那盏靠窗的灯，还有雨点打在铁门上的声音。','声音和光，把那个夜晚留了下来。'],
    ['quiet','E03','玻璃上的小圈','我用手指在上面画了个小圈，看看窗外是不是快天黑了。','等汤的时候，也看了一会儿天色。'],
    ['quiet','E01','有人慢慢读书','我喜欢图书馆里有人愿意慢慢读书的样子','安静的片刻，也值得被看见。']
  ];
  const points=raw.map(([category,episode,title,quote,reflection],i)=>({id:`m${i+1}`,category,episode,title,quote,reflection}));
  const data={categories,episodes,points};
  if(typeof module!=='undefined' && module.exports)module.exports=data;
  else root.MemoryGardenData=data;
})(typeof window==='undefined'?{}:window);
