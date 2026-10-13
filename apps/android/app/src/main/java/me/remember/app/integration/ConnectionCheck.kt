package me.remember.app.integration

import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

enum class ConnectionPhase { UNCHECKED, CHECKING, READY, FAILED, INCOMPATIBLE }
data class ConnectionCheck(val phase: ConnectionPhase = ConnectionPhase.UNCHECKED, val message: String = "")

fun connectedService(info: ServiceInfo): ConnectionCheck {
    if(info.apiVersion.isNotBlank() && info.apiVersion != "0.7.0") {
        return ConnectionCheck(ConnectionPhase.INCOMPATIBLE, "应用与服务版本不匹配，请联系管理员获取对应安装包。")
    }
    if(info.apiVersion.isBlank()) {
        return ConnectionCheck(ConnectionPhase.INCOMPATIBLE, "服务未提供本版应用需要的版本信息，请联系管理员确认。")
    }
    return ConnectionCheck(ConnectionPhase.READY, if(info.registrationAllowed) "服务已连接，可以登录或创建账号。" else "服务已连接，请使用管理员提供的内测账号登录。")
}

fun failedConnection(error: Throwable): ConnectionCheck {
    val causes = generateSequence(error) { it.cause }.take(10).toList()
    val message = when {
        causes.any { it is SSLException } -> "证书验证失败。请检查手机日期并获取最新安装包；不要关闭安全验证。"
        causes.any { it is SocketTimeoutException || it is ConnectException } -> "暂时无法连接服务。请确认网络可用；持续失败时请管理员检查服务器和网络连接。"
        causes.any { it is UnknownHostException } -> "无法找到服务地址，请检查网络和连接设置。"
        error is BackendHttpException && error.status == 403 -> "服务拒绝当前访问，请联系管理员检查网络准入。"
        else -> "服务连接检查未完成，请稍后重试；持续失败时联系管理员。"
    }
    return ConnectionCheck(ConnectionPhase.FAILED, message)
}
