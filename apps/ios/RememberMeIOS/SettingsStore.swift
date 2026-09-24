import Foundation
import Security

struct ServerSettings {
    var baseURL: String
    var token: String
    var subjectID: String
    var recordingConsentID: String
    var cloudTwinConsentID: String

    var validatedURL: URL? {
        guard let url = URL(string: baseURL.trimmingCharacters(in: .whitespacesAndNewlines)),
              ["http", "https"].contains(url.scheme?.lowercased() ?? ""),
              url.host != nil,
              url.user == nil,
              url.password == nil,
              url.query == nil,
              url.fragment == nil,
              url.path.isEmpty || url.path == "/" else {
            return nil
        }
        return url
    }

    var isReady: Bool {
        validatedURL != nil && !token.isEmpty && !subjectID.isEmpty && !recordingConsentID.isEmpty
    }
}

enum SettingsStore {
    private static let service = "me.remember.ios.backend"
    private static let account = "actor-token"

    static func load() -> ServerSettings {
        let defaults = UserDefaults.standard
        return ServerSettings(
            baseURL: defaults.string(forKey: "backendURL") ?? "http://127.0.0.1:8000",
            token: readToken() ?? "",
            subjectID: defaults.string(forKey: "subjectID") ?? "",
            recordingConsentID: defaults.string(forKey: "recordingConsentID") ?? "",
            cloudTwinConsentID: defaults.string(forKey: "cloudTwinConsentID") ?? ""
        )
    }

    static func save(_ settings: ServerSettings) throws {
        let defaults = UserDefaults.standard
        defaults.set(settings.baseURL.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "backendURL")
        defaults.set(settings.subjectID.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "subjectID")
        defaults.set(settings.recordingConsentID.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "recordingConsentID")
        defaults.set(settings.cloudTwinConsentID.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "cloudTwinConsentID")
        try saveToken(settings.token.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private static func readToken() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func saveToken(_ token: String) throws {
        let identity: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        let deleteStatus = SecItemDelete(identity as CFDictionary)
        guard deleteStatus == errSecSuccess || deleteStatus == errSecItemNotFound else {
            throw SettingsError.keychain(deleteStatus)
        }
        guard !token.isEmpty else { return }
        var item = identity
        item[kSecValueData as String] = Data(token.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(item as CFDictionary, nil)
        guard addStatus == errSecSuccess else { throw SettingsError.keychain(addStatus) }
    }
}

enum SettingsError: LocalizedError {
    case keychain(OSStatus)

    var errorDescription: String? {
        switch self {
        case .keychain(let status): return "无法安全保存访问令牌（\(status)）。"
        }
    }
}
