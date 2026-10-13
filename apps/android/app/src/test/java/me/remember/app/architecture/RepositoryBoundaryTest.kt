package me.remember.app.architecture

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class RepositoryBoundaryTest {
    @Test
    fun composablesDoNotConstructRepositories() {
        val sourceRoot = File("src/main/java/me/remember/app")
        val uiRoots = listOf("feature", "navigation", "ui")
        val violations = uiRoots.flatMap { root ->
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

        assertTrue(
            "Compose/UI code must receive repository interfaces from an outer assembly boundary; violations:\n${violations.joinToString("\n")}",
            violations.isEmpty()
        )
    }
}
