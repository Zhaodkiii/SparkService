import hashlib
import json
import re
from pathlib import Path
from .catalog import CATEGORIES


def safe(value):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '-', value).strip('. ')[:100] or '未命名'


def export_library(root, template, rows):
    destination=Path(root)/safe(template.series.title)/safe(template.title)
    destination.mkdir(parents=True,exist_ok=True)
    previous = json.loads((destination/'索引.json').read_text()).get('items',[]) if (destination/'索引.json').exists() else []
    index=[]
    for lib,version,r,original in rows:
        if original is None: raise ValueError('缺少源资源，无法导出')
        category,title=CATEGORIES[r.kind]
        extension={'image/png':'.png','image/webp':'.webp','image/jpeg':'.jpg'}[r.resource.mime]
        folder=(Path('背景库')/title[r.subcategory]) if lib.library_type=='background' else (Path('贴纸库')/category/title[r.subcategory])
        relative=folder/(safe(r.name)+'-'+r.resource_id[:12]+extension)
        preview=Path('预览图')/(r.thumbnail_id+'.webp')
        for path,data,digest in [(relative,original['data'],r.resource_id),(preview,original['thumbnail'],r.thumbnail_id)]:
            target=destination/path
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('导出数据摘要不符')
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():target.write_bytes(data)
            elif hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('已有文件摘要冲突，未覆盖')
        index.append(dict(id=str(r.material_id),revision=r.pk,library_id=str(lib.pk),library_version=version.number,type=lib.library_type,
                          name=r.name,kind=r.kind,subcategory=r.subcategory,keywords=r.keywords,aliases=r.aliases,
                          sha256=r.resource_id,byte_size=r.resource.byte_size,width=r.resource.width,height=r.resource.height,
                          path=relative.as_posix(),thumbnail_path=preview.as_posix(),object_key=r.resource.object_key,sources=r.sources))
    payload=dict(schema_version=1,template_id=str(template.pk),template_title=template.title,preset_version=template.current.number,
                 series=template.series.title,items=index)
    temp=destination/'索引.json.tmp';temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2));temp.replace(destination/'索引.json')
    keep={i[key] for i in index for key in ('path','thumbnail_path')}
    for old in previous:
        for key,digest in [('path',old['sha256']),('thumbnail_path',None)]:
            relative=old.get(key)
            if not relative or relative in keep: continue
            file=(destination/relative).resolve()
            if not file.is_relative_to(destination.resolve()): raise ValueError('旧索引包含不安全路径')
            if file.is_file() and (digest is None or hashlib.sha256(file.read_bytes()).hexdigest()==digest):file.unlink()
    counts={typ:sum(i['type']==typ for i in index) for typ in ('sticker','background')}
    (destination/'使用说明.md').write_text(f"# {template.title}\n\n来自当前已发布预设 v{template.current.number}。贴纸 {counts['sticker']} 项，背景 {counts['background']} 项。\n\n目录与子分类均为中文；索引.json 记录数据库 ID、库版本、OSS 对象路径、原图摘要和来源页。预览图单独存放，不计入素材数量。文件为源资源副本，不修改原预设。\n")
    return destination
