# 云端月度批次：逐题文本复核

批次 relay-compact-cloud-v1。助手读取已保存回答及有效来源后复核；非人工听读。以下结果保留原60问，不用后续12项复测替换。

原批次33项有支持、23项需质量修正、4项漏答；来源/权限/逐字检查0错误。后续修复与12题结果见 [最新记录](GROQ_LIVE_RESULTS_2026-10-08.md)。

|问题|类型|复核|说明|
|---|---|---|---|
|bus_driver-q01|ORIGINAL|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q02|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q03|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q04|SIMULATION|needs_quality_correction|整理出车记录有据，但省略没有代驾，附带无关父亲信息。|
|bus_driver-q05|ORIGINAL|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q06|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q07|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q08|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q09|SIMULATION|needs_quality_correction|主要转述关系正确，未见本人及未查工作记录的限制未展开。|
|bus_driver-q10|SIMULATION|needs_quality_correction|保留讲述者转述，尚可补足未见本人及未查记录的边界。|
|bus_driver-q11|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q12|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q13|ORIGINAL|needs_quality_correction|位置答对，但返回整段原文，附带超出问题的私密背景（Owner）。|
|bus_driver-q14|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q15|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q16|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q17|ORIGINAL|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q18|ORIGINAL|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|bus_driver-q19|SIMULATION|needs_quality_correction|留灯等待的主要原因有据；附带事故否认和性别代词，姓名音近字仍需听读核对。|
|bus_driver-q20|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q01|SIMULATION|needs_quality_correction|答出妈妈，未给姓名；所问关系正确。|
|firefighter-q02|ORIGINAL|needs_quality_correction|答出给妈妈电话，原话包含ASR错字“我打吃过了”。|
|firefighter-q03|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q04|SIMULATION|needs_quality_correction|本子记录当日电话有据，未明说文字记录而非照片。|
|firefighter-q05|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q06|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q07|SIMULATION|needs_quality_correction|时间变化答出，但呈贡写作成贡，附带未问的搬家原因。|
|firefighter-q08|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q09|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q10|SIMULATION|needs_quality_correction|哥哥归属正确，转述应清楚写成讲述者转述队友，避免层次歧义。|
|firefighter-q11|SIMULATION|needs_quality_correction|区分两人正确，但生成回答仍选择了性别代词。|
|firefighter-q12|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q13|UNKNOWN|failed|Owner可见实际ASR明确写出手机私人备忘的位置，回答UNKNOWN，漏答。|
|firefighter-q14|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q15|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q16|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|firefighter-q17|ORIGINAL|needs_quality_correction|否定正确；引用中“他哥哥”的性别字来自ASR，未进行人工听读。|
|firefighter-q18|SIMULATION|needs_quality_correction|核心否定答对，但没有带出喜欢散步的补充。|
|firefighter-q19|UNKNOWN|failed|Owner可见Groq转写明确说明为完整听完唱片而静音，回答UNKNOWN，漏答。|
|firefighter-q20|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|life_review-q01|ORIGINAL|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|life_review-q02|ORIGINAL|needs_quality_correction|形状答出，但展示桌被ASR转成战士桌，原话开头有错字。|
|life_review-q03|SIMULATION|needs_quality_correction|整理样册的对象能追溯材料，但梁舒在ASR中成为梁叔；姓名与关系不算准确。|
|life_review-q04|ORIGINAL|needs_quality_correction|原话保真但ASR把梁舒转成两树，单独展示难以辨认对象。|
|life_review-q05|ORIGINAL|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|life_review-q06|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|life_review-q07|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|life_review-q08|SIMULATION|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|life_review-q09|SIMULATION|needs_quality_correction|转述及未亲眼看见边界保留；李青在ASR中成为李清。|
|life_review-q10|SIMULATION|needs_quality_correction|主要转述关系正确；李青/李清字形问题未修正。|
|life_review-q11|UNKNOWN|failed|Owner材料区分成年客户与女儿同学，回答UNKNOWN；Reader同题却区分成功。|
|life_review-q12|SIMULATION|needs_quality_correction|两人区分正确，姓名沿用ASR李清。|
|life_review-q13|ORIGINAL|needs_quality_correction|位置正确，原话中顾平成为姑平，附带借款背景。|
|life_review-q14|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|life_review-q15|SIMULATION|needs_quality_correction|明确城市和日期未定；女儿名字沿用错误ASR周河。|
|life_review-q16|UNKNOWN|failed|Reader可见材料明确城市和日期未定，回答UNKNOWN；已知未定不等于无信息。|
|life_review-q17|SIMULATION|needs_quality_correction|已知否定答对，但生成回答仍使用他而非讲述者。|
|life_review-q18|ORIGINAL|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
|life_review-q19|SIMULATION|needs_quality_correction|蓝色房子是主要原因，回答却用第一人称，女儿姓名/代词有误且附带无关信息。|
|life_review-q20|UNKNOWN|supported|所问必要事实或UNKNOWN与可见材料一致；不是人工听读或总体准确率证明。|
