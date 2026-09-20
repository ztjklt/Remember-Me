pluginManagement {
    repositories {
        google()
        maven("https://maven-central-asia.storage-download.googleapis.com/maven2/") {
            name = "GoogleCloudMavenCentralMirror"
        }
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        maven("https://maven-central-asia.storage-download.googleapis.com/maven2/") {
            name = "GoogleCloudMavenCentralMirror"
        }
    }
}
rootProject.name = "RememberMe"
include(":app")
