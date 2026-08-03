package com.floris.android.core.share

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

/**
 * 把回答卡片保存到相册（对齐网页端"保存为图片"）。
 *
 * Android 10+ 走 MediaStore，不需要任何存储权限；
 * 更老的系统写入公共 Pictures 目录（清单里已声明 maxSdkVersion 的写权限）。
 */
object ImageSaver {

    private const val ALBUM = "Floris"

    suspend fun saveToGallery(
        context: Context,
        image: ImageBitmap,
        displayName: String = "floris-${System.currentTimeMillis()}",
    ): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            val bitmap = image.asAndroidBitmap()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                saveViaMediaStore(context, bitmap, displayName)
            } else {
                saveToPublicDirectory(context, bitmap, displayName)
            }
        }
    }

    private fun saveViaMediaStore(context: Context, bitmap: Bitmap, name: String): String {
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "$name.png")
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/$ALBUM")
            put(MediaStore.Images.Media.IS_PENDING, 1)
        }
        val resolver = context.contentResolver
        val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
            ?: error("无法创建相册文件")
        try {
            resolver.openOutputStream(uri)?.use { stream ->
                if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                    error("图片编码失败")
                }
            } ?: error("无法写入相册")
            values.clear()
            values.put(MediaStore.Images.Media.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
        } catch (error: Throwable) {
            // 写失败要清掉占位条目，避免相册留下 0 字节的坏图。
            runCatching { resolver.delete(uri, null, null) }
            throw error
        }
        return "已保存到相册 · $ALBUM"
    }

    private fun saveToPublicDirectory(context: Context, bitmap: Bitmap, name: String): String {
        val directory = File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES),
            ALBUM,
        )
        if (!directory.exists() && !directory.mkdirs()) error("无法创建相册目录")
        val file = File(directory, "$name.png")
        FileOutputStream(file).use { stream ->
            if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                error("图片编码失败")
            }
        }
        // 让系统相册立刻能看到这张图。
        MediaStore.Images.Media.insertImage(context.contentResolver, file.absolutePath, name, null)
        return "已保存到相册 · $ALBUM"
    }
}
