package me.remember.app.model

data class Subject(val id:String,val name:String,val role:String,val city:String)
data class Actor(val id:String,val name:String,val relationship:String)
data class Memory(val id:String,val date:String,val place:String,val story:String,val people:List<String>,val tags:List<String>,val duration:String,
    val sourceRecordingPath:String?=null,val evidence:String="",val sourceType:String="SUBJECT")
data class TwinReply(val question:String,val original:String?,val simulation:String)
data class LegacyProfile(val subject:Subject,val years:String,val recordings:Int,val stories:Int,val privateMessages:Int)
sealed interface Loadable<out T>{ data object Loading:Loadable<Nothing>; data class Content<T>(val value:T):Loadable<T>; data object Empty:Loadable<Nothing>; data class Error(val message:String):Loadable<Nothing> }
