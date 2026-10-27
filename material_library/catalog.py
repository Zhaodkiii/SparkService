CATEGORIES = {
 'background': ('背景', {'paper_texture':'纸张纹理','page':'整页底图','scene':'场景底图'}),
 'photo': ('相框与照片卡', {'frame':'相框','photo_card':'照片卡'}),
 'paper': ('纸卡与票据', {'note':'便签','checklist':'清单卡','route':'路线卡','ticket':'票据','title_card':'标题底板'}),
 'text': ('文字贴纸', {'title':'标题','body':'正文','date':'日期','quote':'引语','caption':'照片说明'}),
 'illustration': ('插画与装饰', {'scene':'场景插画','object':'主题物件','botanical':'花草','tape':'胶带','stamp':'装饰印章','ornament':'其他装饰'}),
 'branding': ('品牌标识', {'logo':'品牌标志','seal':'品牌印章','series_mark':'系列标志'}),
}
ALIASES = {'便条':'便签','记事纸':'便签','花窗':'窗框','纸胶带':'胶带','纸纹':'纹理','纹理纸':'纹理'}

def validate_category(kind, subcategory, material_type):
    from .models import MaterialCategory
    if kind not in CATEGORIES or (kind == 'background') != (material_type == 'background'):
        raise ValueError('素材分类与库类型不匹配')
    override=MaterialCategory.objects.filter(kind=kind,subcategory=subcategory).first()
    if (override is not None and not override.active) or (override is None and subcategory not in CATEGORIES[kind][1]):
        raise ValueError('分类不存在或已停用')


def legacy_category(name, render_kind):
    """Return stable layer semantics from authored PSD layer names."""
    n = name
    if n.startswith(('照片_', 'photo_照片_')):
        return 'photo', 'slot'
    if n.startswith(('照片卡_', '相框纸卡_')):
        return 'photo', 'photo_card'
    if n.startswith(('相框', '画框')):
        return 'photo', 'frame'
    if n.startswith('照片组件_'):
        return 'photo', 'fixed'
    if n.startswith('背景'):
        if any(x in n for x in ('纸', '纹理', '旧纸', '米白', '米黄')):
            return 'background', 'paper_texture'
        if n == '背景' or '页面底图' in n or n.startswith('背景组件_'):
            return 'background', 'page'
        return 'background', 'scene'
    if n.startswith(('纸卡_', '纸签_', '纸笺_', '纸条_', '纸片背景_', '纸条背景_', '票签背景_', '标题纸卡_', '副标题纸条_', '正文纸卡_', '引语纸条_', '署名纸条_', '卡片_', '记录卡_')):
        if any(x in n for x in ('清单', '想记住的事')):
            return 'paper', 'checklist'
        if any(x in n for x in ('路线', '漫步')):
            return 'paper', 'route'
        if any(x in n for x in ('车票', '票签', '码头', '船票')):
            return 'paper', 'ticket'
        if '标题' in n:
            return 'paper', 'title_card'
        return 'paper', 'note'
    if n.startswith('文字图像'):
        if any(x in n for x in ('日期', '出发日_')):
            return 'text', 'date'
        if any(x in n for x in ('引语', '引言', '寄语', '诗句')):
            return 'text', 'quote'
        if any(x in n for x in ('照片说明', '图注', '来源说明', '页脚')):
            return 'text', 'caption'
        if any(x in n for x in ('标题', '题字', '副标题')):
            return 'text', 'title'
        return 'text', 'body'
    if n.startswith('品牌Logo_') or n.lower() == 'logo':
        return 'branding', 'logo'
    if n.startswith(('装饰', '拼贴', '胶带')):
        if '胶带' in n or n.startswith('胶带'):
            return 'illustration', 'tape'
        if '印章' in n or '红印' in n:
            return 'illustration', 'stamp'
        if any(x in n for x in ('花', '枝', '叶', '桂', '荷', '玉兰')):
            return 'illustration', 'botanical'
        if any(x in n for x in ('园林', '湖景', '古镇', '水巷', '街景')):
            return 'illustration', 'scene'
        return 'illustration', 'ornament'
    if n.startswith('组件_'):
        if any(x in n for x in ('照片', '主景')):
            return 'photo', 'fixed'
        if any(x in n for x in ('车票', '码头')):
            return 'paper', 'ticket'
        if '路线' in n:
            return 'paper', 'route'
        if any(x in n for x in ('清单', '便签', '纸片', '底板')):
            return 'paper', 'checklist' if '清单' in n else 'title_card' if '标题' in n else 'note'
        if '印章' in n:
            return 'illustration', 'stamp'
        if any(x in n for x in ('花', '枝', '叶', '桂', '荷')):
            return 'illustration', 'botanical'
        if any(x in n for x in ('线稿', '古镇', '园林', '水巷', '街景', '路线')):
            return 'illustration', 'scene'
        return 'illustration', 'object'
    if render_kind == 'photo':
        return 'photo', 'slot'
    if render_kind == 'text':
        return 'text', 'body'
    return 'illustration', 'ornament'
