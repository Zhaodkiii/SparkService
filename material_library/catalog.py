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
    if kind not in CATEGORIES or subcategory not in CATEGORIES[kind][1] or (kind == 'background') != (material_type == 'background'):
        raise ValueError('素材分类与库类型不匹配')
