pluginManagement {
    repositories {
        google()
        // Google's mirror of Maven Central (Central itself rate-limits shared CI/cloud IPs)
        maven("https://maven-central.storage-download.googleapis.com/maven2/")
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        // Google's mirror of Maven Central (Central itself rate-limits shared CI/cloud IPs)
        maven("https://maven-central.storage-download.googleapis.com/maven2/")
        mavenCentral()
    }
}
rootProject.name = "Ember"
include(":app")
