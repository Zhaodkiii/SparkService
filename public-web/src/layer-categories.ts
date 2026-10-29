export const layerCategories=[
 {id:'background',title:'背景',icon:'▧'},
 {id:'photo',title:'照片',icon:'▣'},
 {id:'paper',title:'纸卡',icon:'▱'},
 {id:'text',title:'文字',icon:'T'},
 {id:'illustration',title:'装饰',icon:'✦'},
]
export function layerCategory(layer:any,inherited?:string):string|undefined{
 if(layer.semanticKind)return layer.semanticKind
 // PresetLayer.drawingKind and semanticKind are separate in iOS:
 // schema-v2 kind is an explicit semantic even when renderType is group.
 if(layer.renderType&&['background','photo','paper','text','illustration','branding'].includes(layer.kind))return layer.kind
 if(layer.category==='textImage')return 'text'
 if(layer.isLibraryBackground)return 'background'
 // Native template objects carry semantic kinds on their outer groups.
 if(inherited)return inherited
 if(['background','photo','paper','text','illustration','branding'].includes(layer.kind))return layer.kind
 if(layer.kind==='frame')return 'photo'
 if(layer.kind==='sticker')return 'illustration'
 return undefined
}

/** Traverse objects without dropping mixed children when a parent category is off. */
export function visibleLayerIds(objects:Record<string,any>,root:string,hidden:string[]):string[]{
 const result:string[]=[]
 function visit(id:string,inherited?:string,ancestors=new Set<string>()){
  if(ancestors.has(id))throw Error('模板对象循环引用')
  const content=objects[id];if(!content)throw Error('模板缺少图层')
  const next=new Set(ancestors);next.add(id)
  for(const layer of content.layers||[]){
   if(layer.visible===false)continue
   const category=layerCategory(layer,inherited)
   if(layer.contentID)visit(layer.contentID,category,next)
   else if(!category||!hidden.includes(category))result.push(layer.id)
  }
 }
 visit(root);return result
}
