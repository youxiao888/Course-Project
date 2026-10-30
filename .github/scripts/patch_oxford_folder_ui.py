#!/usr/bin/env python3
"""Create Android SAF tree importer for complete Oxford MDX/MDD resource folders."""
from pathlib import Path
b=Path("app/src/main/java/com/galaxy/airviewdictionary")
def edit(p,old,new):
 p=Path(p);s=p.read_text("utf8")
 if s.count(old)!=1:raise RuntimeError(str(p)+" expected 1 match got "+str(s.count(old))+" "+old[:100])
 p.write_text(s.replace(old,new,1),"utf8")
 print("edited",p)
d=b/"data/local/dictionary"
(d/"OxfordFolderImporter.kt").write_text(r'''package com.galaxy.airviewdictionary.data.local.dictionary

import android.content.Context
import android.net.Uri
import android.os.StatFs
import android.provider.DocumentsContract
import android.provider.DocumentsContract.Document
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Path

/** Android SAF directory importer: all resources, including MDD > 2 GiB. */
internal object OxfordFolderImporter {
    data class Progress(
        val index:Int, val count:Int, val name:String,
        val copied:Long, val total:Long
    )
    data class Report(val id:String,val count:Int,val bytes:Long)
    private data class Item(val relative:String,val uri:Uri,val size:Long)

    private fun findFiles(ctx:Context,tree:Uri):List<Item> {
        val out=ArrayList<Item>()
        val visited=HashSet<String>()
        val columns=arrayOf(
            Document.COLUMN_DOCUMENT_ID,Document.COLUMN_DISPLAY_NAME,
            Document.COLUMN_MIME_TYPE,Document.COLUMN_SIZE
        )
        fun recurse(parent:String,relative:String,depth:Int) {
            require(depth<7){"文件夹嵌套超过安全上限"}
            require(visited.add(parent)){"文件夹包含循环链接"}
            val children=DocumentsContract.buildChildDocumentsUriUsingTree(tree,parent)
            val cursor=ctx.contentResolver.query(children,columns,null,null,null)
                ?:error("无法列出文件夹")
            cursor.use{c->
                val idCol=c.getColumnIndexOrThrow(Document.COLUMN_DOCUMENT_ID)
                val nameCol=c.getColumnIndexOrThrow(Document.COLUMN_DISPLAY_NAME)
                val mimeCol=c.getColumnIndexOrThrow(Document.COLUMN_MIME_TYPE)
                val sizeCol=c.getColumnIndex(Document.COLUMN_SIZE)
                while(c.moveToNext()){
                    require(out.size<3000){"文件过多"}
                    val id=c.getString(idCol)
                    val name=(c.getString(nameCol) ?: "").trim()
                    require(name.isNotBlank() && name!="." && name!=".." &&
                        '/' !in name && '\\' !in name && '\u0000' !in name) {
                        "文件夹包含不安全的文件名"
                    }
                    val part=if(relative.isEmpty())name else relative+"/"+name
                    if(c.getString(mimeCol)==Document.MIME_TYPE_DIR){
                        recurse(id,part,depth+1)
                    }else{
                        val size=if(sizeCol>=0 && !c.isNull(sizeCol))
                            c.getLong(sizeCol) else -1L
                        out.add(Item(part,DocumentsContract.buildDocumentUriUsingTree(tree,id),size))
                    }
                }
            }
        }
        recurse(DocumentsContract.getTreeDocumentId(tree),"",0)
        require(out.any {it.relative.endsWith(".mdx",true)}){
            "所选文件夹没有 MDX，请选择包含 oaldpe.mdx 的 OALDPE 文件夹"
        }
        return out
    }

    suspend fun import(
        ctx:Context,tree:Uri,
        onProgress:suspend (Progress)->Unit
    ):Report=withContext(Dispatchers.IO){
        val files=findFiles(ctx,tree)
        val total=files.filter{it.size>0}.sumOf{it.size}
        val root=File(ctx.filesDir,"mdict").apply{mkdirs()}
        val collections=File(root,"collections").apply{mkdirs()}
        val reserve=256L*1024L*1024L
        if(total>0 && StatFs(ctx.filesDir.absolutePath).availableBytes < total+reserve)
            error("可用空间不足。词库约 "+(total/(1024*1024))+" MiB，请预留额外 256 MiB")
        val stage=File(root,".incoming-"+System.nanoTime())
        check(stage.mkdirs()){"临时目录创建失败"}
        var committed=false
        var bytes=0L
        var reported=0L
        try{
            for((i,item) in files.withIndex()){
                currentCoroutineContext().ensureActive()
                val dest=File(stage,item.relative)
                check(dest.parentFile?.mkdirs()==true || dest.parentFile?.isDirectory==true){
                    "无法创建子目录"
                }
                val input=ctx.contentResolver.openInputStream(item.uri)
                    ?:error("无法读取 "+item.relative)
                var fileBytes=0L
                input.use{source->
                    FileOutputStream(dest).buffered(512*1024).use{out->
                        val buffer=ByteArray(512*1024)
                        while(true){
                            currentCoroutineContext().ensureActive()
                            val n=source.read(buffer)
                            if(n<0)break
                            if(n==0)continue
                            out.write(buffer,0,n)
                            fileBytes+=n.toLong()
                            bytes+=n.toLong()
                            if(bytes-reported>=16L*1024*1024){
                                reported=bytes
                                onProgress(Progress(i+1,files.size,item.relative,bytes,total))
                                if(StatFs(ctx.filesDir.absolutePath).availableBytes<reserve/2)
                                    error("磁盘空间不足，已自动停止并清理未完成导入")
                            }
                        }
                        out.flush()
                    }
                }
                if(item.size>=0 && fileBytes!=item.size)
                    error("文件复制不完整："+item.relative)
                onProgress(Progress(i+1,files.size,item.relative,bytes,total))
            }
            currentCoroutineContext().ensureActive()
            val mdx=stage.walkTopDown().firstOrNull{it.isFile && it.extension.equals("mdx",true)}
                ?:error("缺少 MDX")
            val cls=Class.forName("io.github.eb4j.mdict.MDictDictionary")
            cls.getMethod("loadDictionary",Path::class.java).invoke(null,mdx.toPath())
            val collection=File(collections,"oaldpe-"+System.currentTimeMillis())
            check(stage.renameTo(collection)){"导入完成后无法发布词库"}
            committed=true
            Report(collection.name,files.size,bytes)
        } finally{
            if(!committed)stage.deleteRecursively()
        }
    }
}
''',"utf8")
p=str(b/"ui/screen/dictionary/DictionaryActivity.kt")
edit(p,"import android.content.Intent",
     "import android.content.Intent\nimport com.galaxy.airviewdictionary.data.local.dictionary.OxfordFolderImporter")
edit(p,
     '    private var message by mutableStateOf("")',
     '''    private var message by mutableStateOf("")
    private var importing by mutableStateOf(false)
    private var fraction by mutableFloatStateOf(0f)
    private var folderImportJob: kotlinx.coroutines.Job?=null''')
edit(p,
     '    private val chooseFile=registerForActivityResult(ActivityResultContracts.OpenDocument())',
     '''    private val chooseFolder=registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if(uri!=null && !importing){
            // Persist the user-approved SAF tree only. No broad storage permission.
            runCatching {
                contentResolver.takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            importing=true
            fraction=0f
            message="正在检查文件夹…"
            folderImportJob=lifecycleScope.launch {
                try{
                    val report=OxfordFolderImporter.import(this@DictionaryActivity,uri){p->
                        withContext(Dispatchers.Main){
                            fraction=if(p.total>0) (p.copied.toDouble()/p.total).toFloat()
                                .coerceIn(0f,1f) else p.index.toFloat()/p.count
                            message="导入 "+p.index+"/"+p.count+": "+p.name+
                                " · "+(p.copied/(1024*1024))+" MiB"
                        }
                    }
                    version++
                    fraction=1f
                    message="完整词库导入成功，共 "+report.count+" 个文件，"+
                        (report.bytes/(1024*1024))+" MiB"
                }catch(e:kotlinx.coroutines.CancellationException){
                    message="导入已取消，未发布不完整词库"
                    throw e
                }catch(e:Exception){
                    message="导入失败："+(e.cause?.message ?: e.message)
                }finally{importing=false}
            }
        }
    }

    private val chooseFile=registerForActivityResult(ActivityResultContracts.OpenDocument())''')
edit(p,
     '''                    TextButton(onClick={
                        chooseFile.launch(arrayOf("text/*","application/octet-stream","*/*"))
                    }) { Text("导入") }''',
     '''                    TextButton(enabled=!importing,onClick={chooseFolder.launch(null)}) {
                        Text("导入整个文件夹")
                    }
                    TextButton(enabled=!importing,onClick={
                        chooseFile.launch(arrayOf("text/*","application/octet-stream","*/*"))
                    }) { Text("单文件") }''')
edit(p,
     '''                if(message.isNotEmpty()) Text(message,fontSize=12.sp,color=Color(0xFF3267A0))
                Column(''',
     '''                if(message.isNotEmpty()) Text(message,fontSize=12.sp,color=Color(0xFF3267A0))
                if(importing){
                    LinearProgressIndicator(
                        progress={fraction},
                        modifier=Modifier.fillMaxWidth().padding(vertical=8.dp)
                    )
                    TextButton(onClick={folderImportJob?.cancel()}) {Text("取消导入")}
                }
                Column(''')
print("Oxford SAF folder import module & UI applied")
