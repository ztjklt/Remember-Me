package me.remember.app.architecture

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class RepositoryBoundaryTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Test
    fun composablesDoNotConstructRepositories() {
        val sourceRoot = File("src/main/java/me/remember/app")
        val violations = findRepositoryConstructions(sourceRoot)

        assertTrue(
            "Compose/UI code must receive repository interfaces from an outer assembly boundary; violations:\n${violations.joinToString("\n")}",
            violations.isEmpty()
        )
    }

    @Test
    fun reportsRepositoryConstructionReintroducedInUiSource() {
        val sourceRoot = temporaryFolder.newFolder("app")
        val featureDir = File(sourceRoot, "feature").apply { mkdirs() }
        File(featureDir, "OffendingScreen.kt").writeText(
            "package me.remember.app.feature\n" +
                "private val repository = MockRememberMeRepository()\n"
        )

        val violations = findRepositoryConstructions(sourceRoot)

        assertTrue(
            "Expected the UI repository-construction guard to report the offending source",
            violations.any { it.contains("OffendingScreen.kt:2") }
        )
    }

    private fun findRepositoryConstructions(sourceRoot: File): List<String> {
        val uiRoots = listOf("feature", "navigation", "ui")
        return uiRoots.flatMap { root ->
            File(sourceRoot, root).walkTopDown()
                .filter { it.isFile && it.extension == "kt" }
                .flatMap { file ->
                    file.readLines().mapIndexedNotNull { index, line ->
                        if (line.contains("Repository(") || line.contains("Repository {")) {
                            "${file.relativeTo(sourceRoot).path}:${index + 1}: $line"
                        } else null
                    }
                }
                .toList()
        }
    }
}
