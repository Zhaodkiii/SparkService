from rest_framework import serializers as s

class Face(s.Serializer):
    id = s.RegexField(r'^[A-Za-z0-9_-]{1,80}$')
    asset_id = s.UUIDField()
    postscript_name = s.CharField(max_length=180)
    label = s.CharField(max_length=80)

class Recipe(s.Serializer):
    text = s.CharField(max_length=80, default='把日子写成诗')
    background = s.RegexField(r'^#[0-9a-fA-F]{6}$', default='#FFF6EB')
    color = s.RegexField(r'^#[0-9a-fA-F]{6}$', default='#54483E')
    decoration = s.ChoiceField(choices=['flowers','stars','paper'], default='flowers')

class Content(s.Serializer):
    title = s.CharField(max_length=120)
    author = s.CharField(max_length=120, allow_blank=True, default='')
    description = s.CharField(max_length=2000, allow_blank=True, default='')
    styles = s.ListField(child=s.CharField(max_length=30), max_length=15, default=list)
    languages = s.ListField(child=s.CharField(max_length=30), max_length=15, default=list)
    aliases = s.ListField(child=s.CharField(max_length=60), max_length=30, default=list)
    faces = Face(many=True, default=list)
    default_face = s.CharField(max_length=80, allow_blank=True, default='')
    cover = s.UUIDField(allow_null=True, default=None)
    previews = s.ListField(child=s.UUIDField(), max_length=10, default=list)
    license_asset = s.UUIDField(allow_null=True, default=None)
    license_source = s.URLField(allow_blank=True, default='')
    license_approved = s.BooleanField(default=False)
    license_scopes = s.ListField(child=s.ChoiceField(choices=['app','distribution','paid_service','print']), default=list)
    license_note = s.CharField(max_length=2000, allow_blank=True, default='')
    recipe = Recipe(default=dict)

class UploadInput(s.Serializer):
    family = s.UUIDField()
    kind = s.ChoiceField(choices=['font','cover','preview','license'])
    name = s.CharField(max_length=160)
    byte_size = s.IntegerField(min_value=1, max_value=100*1024*1024)
    mime = s.ChoiceField(choices=['font/ttf','font/otf','image/png','image/webp','application/pdf','text/plain'])
    md5 = s.CharField(max_length=24)
    sha256 = s.RegexField(r'^[a-f0-9]{64}$')
    def validate(self, value):
        import base64
        try:
            if len(base64.b64decode(value['md5'], validate=True)) != 16: raise ValueError()
        except Exception: raise s.ValidationError('无效 MD5')
        allowed={'font':['font/ttf','font/otf'],'cover':['image/png','image/webp'],'preview':['image/png','image/webp'],'license':['application/pdf','text/plain']}
        if value['mime'] not in allowed[value['kind']]: raise s.ValidationError('文件类型不匹配')
        return value
