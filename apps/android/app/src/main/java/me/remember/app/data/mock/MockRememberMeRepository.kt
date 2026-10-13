package me.remember.app.data.mock

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import me.remember.app.data.repository.*
import me.remember.app.model.*

class MockRememberMeRepository:MemoryRepository,PersonModelRepository,LegacyRepository,TwinService {
    private val chen=Subject("subject-chen","陈屿","独立纪录片剪辑师","杭州")
    override fun subject():Flow<Loadable<Subject>> = flowOf(Loadable.Content(chen))
    override fun memories():Flow<Loadable<List<Memory>>> = flowOf(Loadable.Content(listOf(
        Memory("m1","2012","襄阳","那年夏天，我第一次帮外婆整理老照片。她记得每个人拍照时的心情。",listOf("外婆"),listOf("家人","成长"),"00:42"),
        Memory("m2","2019","广州","第一次独立完成一部短片以后，我才承认自己真的想做影像。",listOf("林舟"),listOf("选择","创造"),"01:18"),
        Memory("m3","2024","杭州","搬来杭州不是为了更安稳，而是想把生活过得更诚实一点。",listOf("许宁"),listOf("城市","价值观"),"00:56")
    )))
    override fun legacyProfile():Flow<Loadable<LegacyProfile>> = flowOf(Loadable.Content(LegacyProfile(Subject("legacy-lan","林岚","母亲","武汉"),"1968 — 2047",127,43,6)))
    override suspend fun respond(question:String)=TwinReply(question,"你曾经说过：我最喜欢外婆家窗边那只旧收音机。","Based on what you’ve told me… 你珍惜的也许不是那台收音机本身，而是它让一家人安静地待在一起。")
}
