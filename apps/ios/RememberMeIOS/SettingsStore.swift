import Foundation
import Security

struct ServerSettings {
    var baseURL: String
    var token: String
    var subjectID: String
    var recordingConsentID: String
    var cloudTwinConsentID: String
    var handoverConsentID: String
    var voiceConsentID: String

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
    private static let refreshAccount = "refresh-token"

    static var email: String { UserDefaults.standard.string(forKey: "accountEmail") ?? "" }
    static var refreshToken: String { readSecret(refreshAccount) ?? "" }

    static func load() -> ServerSettings {
        #if DEBUG
        importLocalDevelopmentConnection()
        #endif
        return storedSettings()
    }

    private static func storedSettings() -> ServerSettings {
        let defaults = UserDefaults.standard
        return ServerSettings(
            baseURL: defaults.string(forKey: "backendURL") ?? "http://127.0.0.1:8000",
            token: readSecret(account) ?? "",
            subjectID: defaults.string(forKey: "subjectID") ?? "",
            recordingConsentID: defaults.string(forKey: "recordingConsentID") ?? "",
            cloudTwinConsentID: defaults.string(forKey: "cloudTwinConsentID") ?? "",
            handoverConsentID: defaults.string(forKey: "handoverConsentID") ?? "",
            voiceConsentID: defaults.string(forKey: "voiceConsentID") ?? ""
        )
    }

    #if DEBUG
    private struct LocalDevelopmentConnection: Decodable {
        let baseURL: String
        let token: String
        let subjectID: String
        let email: String?
        let refreshToken: String?
    }

    private static func importLocalDevelopmentConnection() {
        guard let documents = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask
        ).first else { return }
        let file = documents.appendingPathComponent("rememberme-local-connection.json")
        guard FileManager.default.fileExists(atPath: file.path) else { return }
        // A development handoff must never replace a signed-in person's
        // credential or Subject. Discard the plaintext file if it is stale.
        guard email.isEmpty && refreshToken.isEmpty && readSecret(account) == nil else {
            try? FileManager.default.removeItem(at: file)
            return
        }
        guard let data = try? Data(contentsOf: file),
              let connection = try? JSONDecoder().decode(LocalDevelopmentConnection.self, from: data) else {
            try? FileManager.default.removeItem(at: file)
            return
        }
        let settings = ServerSettings(
            baseURL: connection.baseURL, token: connection.token,
            subjectID: connection.subjectID, recordingConsentID: "",
            cloudTwinConsentID: "", handoverConsentID: "", voiceConsentID: ""
        )
        guard settings.validatedURL != nil, !settings.token.isEmpty,
              !settings.subjectID.isEmpty else { return }
        do {
            if let email = connection.email, !email.isEmpty,
               let refresh = connection.refreshToken, !refresh.isEmpty {
                try save(settings)
                try saveSecret(refresh, for: refreshAccount)
                UserDefaults.standard.set(email, forKey: "accountEmail")
            } else {
                try save(settings)
            }
            try FileManager.default.removeItem(at: file)
            UserDefaults.standard.removeObject(forKey: "developmentImportError")
        } catch {
            UserDefaults.standard.set(error.localizedDescription, forKey: "developmentImportError")
        }
    }

    #endif

    static func save(_ settings: ServerSettings) throws {
        try saveSecret(settings.token.trimmingCharacters(in: .whitespacesAndNewlines), for: account)
        persistMetadata(settings)
    }

    private static func persistMetadata(_ settings: ServerSettings) {
        let defaults = UserDefaults.standard
        defaults.set(settings.baseURL.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "backendURL")
        defaults.set(settings.subjectID.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "subjectID")
        defaults.set(settings.recordingConsentID.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "recordingConsentID")
        defaults.set(settings.cloudTwinConsentID.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "cloudTwinConsentID")
        defaults.set(settings.handoverConsentID.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "handoverConsentID")
        defaults.set(settings.voiceConsentID.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "voiceConsentID")
    }

    static func saveAccount(email: String, accessToken: String, refreshToken: String, subjectID: String) throws {
        guard !email.isEmpty, !accessToken.isEmpty, !refreshToken.isEmpty,
              !subjectID.isEmpty else { throw SettingsError.invalidAccount }
        var settings = storedSettings()
        if settings.subjectID != subjectID {
            settings.recordingConsentID = ""
            settings.cloudTwinConsentID = ""
            settings.handoverConsentID = ""
            settings.voiceConsentID = ""
        }
        settings.subjectID = subjectID
        settings.token = accessToken
        let previousAccess = readSecret(account) ?? ""
        let previousRefresh = readSecret(refreshAccount) ?? ""
        // Publish the new Subject and email only after both credentials are
        // safely stored. A failed second write restores the old session.
        try saveSecret(refreshToken, for: refreshAccount)
        do {
            try saveSecret(accessToken, for: account)
        } catch {
            let refreshRestored = (try? saveSecret(previousRefresh, for: refreshAccount)) != nil
            let accessRestored = (try? saveSecret(previousAccess, for: account)) != nil
            if !refreshRestored || !accessRestored {
                UserDefaults.standard.removeObject(forKey: "accountEmail")
                UserDefaults.standard.removeObject(forKey: "subjectID")
            }
            throw error
        }
        persistMetadata(settings)
        UserDefaults.standard.set(email, forKey: "accountEmail")
    }

    static func clearAccount() throws {
        let defaults = UserDefaults.standard
        for key in ["accountEmail", "subjectID", "recordingConsentID", "cloudTwinConsentID",
                    "handoverConsentID", "voiceConsentID"] {
            defaults.removeObject(forKey: key)
        }
        // Fail closed in the UI even if Keychain deletion fails.
        let accessError = Result { try saveSecret("", for: account) }.failure
        let refreshError = Result { try saveSecret("", for: refreshAccount) }.failure
        if let error = accessError ?? refreshError { throw error }
    }

    private static func readSecret(_ name: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: name,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func saveSecret(_ token: String, for name: String) throws {
        let identity: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: name
        ]
        if token.isEmpty {
            let status = SecItemDelete(identity as CFDictionary)
            guard status == errSecSuccess || status == errSecItemNotFound else {
                throw SettingsError.keychain(status)
            }
            return
        }
        let bytes = Data(token.utf8)
        let updateStatus = SecItemUpdate(identity as CFDictionary, [kSecValueData as String: bytes] as CFDictionary)
        if updateStatus == errSecSuccess { return }
        guard updateStatus == errSecItemNotFound else { throw SettingsError.keychain(updateStatus) }
        var item = identity
        item[kSecValueData as String] = bytes
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(item as CFDictionary, nil)
        guard addStatus == errSecSuccess else { throw SettingsError.keychain(addStatus) }
    }
}

enum SettingsError: LocalizedError {
    case keychain(OSStatus)
    case invalidAccount

    var errorDescription: String? {
        switch self {
        case .keychain(let status): return "无法安全保存访问令牌（\(status)）。"
        case .invalidAccount: return "账号响应缺少必要凭证，请重新登录。"
        }
    }
}

private extension Result {
    var failure: Failure? {
        if case .failure(let error) = self { return error }
        return nil
    }
}
