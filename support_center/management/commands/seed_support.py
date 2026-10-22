from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from support_center.models import Category,Article,ArticleVersion,Config
from backoffice.rbac import bootstrap_admin_permissions
from notification_center.business_scenes import sync_business_scenes

CONTENT=[
 ('editing','手帐编辑与保存','手帐如何保存？','编辑中的修改由应用保存到本机作品目录。离开前请确认没有保存失败提示。保存失败时保留原界面并重试，不要卸载应用。'),
 ('editing','手帐编辑与保存','换设备能恢复手帐吗？','当前登录和文件上传不代表手帐已完成云端备份。请保留拥有作品的原设备。图片和 PDF 用于阅读，不包含可恢复编辑的全部图层与草稿。'),
 ('editing','手帐编辑与保存','图片和 PDF 是作品原件吗？','图片和 PDF 是阅读用导出副本，不等同于可编辑作品备份。保留本机原件后仍可继续编辑；请勿只因已导出就删除原作品。'),
 ('storage','存储与恢复','误删作品如何恢复？','进入设置 → 存储空间 → 最近删除，选择整本手帐恢复。删除页面可在对应手帐的存储详情查看恢复入口。永久删除无法通过最近删除恢复。'),
 ('storage','存储与恢复','安全清理会删除什么？','安全清理用于可重建预览和符合条件的过期导出副本。作品、草稿、原图和下载包不参加安全清理。手动永久删除作品前请检查内容。'),
 ('photos','照片与素材','照片或相机权限被拒绝怎么办？','打开 iOS 系统设置，找到本应用，按需要调整照片与相机权限。返回应用后重新进入相应功能。仅提供部分照片时，请检查所需照片是否已授权。'),
 ('photos','照片与素材','模板下载失败怎么办？','检查网络与设备剩余空间，在下载管理中查看失败原因并重试。未完成下载不表示已经成功添加作品；请确认内容完整后再进入编辑。'),
 ('export','导出与印制','导出失败怎么办？','先检查可用空间、相册权限和页面素材是否可读取，再重新导出。请保留原作品。仍失败时，可在反馈中描述格式、页数和提示，并附错误截图。'),
 ('export','导出与印制','如何查询印制订单和售后？','进入设置 → 我的印制订单，选择订单查看付款、制作和物流进度。退款、品质等问题优先使用订单详情的售后入口；一般反馈不会直接修改订单或发起退款。'),
 ('custom','专属定制','如何查询专属定制进度？','进入定制 Tab 查看对应需求。工作人员要求补充资料时，请在原需求中操作；成品交付后按页面提示查看并添加到我的手帐。'),
 ('account','账号与登录','切换账号后作品不见了怎么办？','作品与账号隔离。请确认当前登录方式与原账号一致，切回原账号查看。退出登录不会主动删除本机作品，但登录不代表作品具有云端备份。')]

class Command(BaseCommand):
    help='创建首发帮助内容及权限；默认暂停受理，不覆盖已有运营内容'
    @transaction.atomic
    def handle(self,*args,**options):
        Config.objects.get_or_create(key='traveldiary');bootstrap_admin_permissions();sync_business_scenes()
        created=0
        for index,(code,name,title,body) in enumerate(CONTENT):
            c,_=Category.objects.get_or_create(code=code,defaults={'name':name,'sort':index})
            if Article.objects.filter(category=c,draft__title=title).exists():continue
            content=dict(title=title,body=body,summary='',keywords='',pinned=False,sort=index,language='zh-Hans',min_version='',max_version='')
            a=Article.objects.create(category=c,draft=content,published=content,live=True,ever_published=True,published_at=timezone.now())
            ArticleVersion.objects.create(article=a,content=content);created+=1
        self.stdout.write(self.style.SUCCESS(f'新增 {created} 篇帮助；受理状态保持原配置。请配置客服权限、服务时间和受理开关。'))
