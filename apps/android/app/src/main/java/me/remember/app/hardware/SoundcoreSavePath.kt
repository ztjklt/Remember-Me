package me.remember.app.hardware

import java.io.File

/** Vendor 1.3.02 builds paths by concatenating folder + fileId + .opus. */
object SoundcoreSavePath {
    @JvmStatic fun directoryArgument(directory: File): String {
        val root = directory.canonicalFile
        require(root.isDirectory) { "Create the app-private download directory first" }
        return root.path.trimEnd(File.separatorChar) + File.separator
    }
}
