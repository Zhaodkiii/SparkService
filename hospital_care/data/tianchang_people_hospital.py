"""天长市人民医院官网公开演示数据。

数据来源：
* https://www.tcsyy.com/cms/a/523.html
* https://www.tcsyy.com/cms/c/neisanke.html
* 各医生详情页见 ``DOCTORS``。

本快照只收录用户指定的内三科页面公开医生，不把医院官网其他科室目录误当成已抓取的医生数据。
"""

from __future__ import annotations


SOURCE_UPDATED_AT = "2026-09-20"
HOSPITAL_SOURCE_URL = "https://www.tcsyy.com/cms/a/523.html"
DEPARTMENT_SOURCE_URL = "https://www.tcsyy.com/cms/c/neisanke.html"

HOSPITAL = {
    "code": "000002",
    "name": "天长市人民医院",
    "short_name": "天长人民医院",
    "grade": "三级综合性医院",
    "province_code": "340000",
    "city_code": "341100",
    "district_code": "341181",
    "address": "安徽省滁州市天长市建设东路194号",
    "service_phone": "0550-7022048",
    "emergency_phone": "120",
    "website_url": "https://www.tcsyy.com/",
    "logo_url": "https://www.tcsyy.com/assets/addons/cms/2023/20150703140323475_SJ6jpDCj.jpg",
    "introduction": (
        "天长市人民医院是一家融医疗、教学、科研为一体的三级综合性医院，始建于1949年2月。"
        "医院占地87亩，建筑面积9.28万平方米，开放床位950张；官网公开资料显示，"
        "医院设有19个一级学科、21个二级学科、21个独立专业病区、20个医技科室、"
        "综合性门诊部和健康体检部。以上资料来自医院官网公开页面，仅用于产品演示。"
    ),
}

_DEPARTMENT_NAMES = [
    ("CLIN_BONE_1", "骨一科"), ("CLIN_OBGYN", "妇产科"), ("SURG_3", "外三科"),
    ("SURG_NEURO", "神经外科"), ("SURG_1", "外一科"), ("ENT", "耳鼻咽喉科"),
    ("DENTAL", "口腔科"), ("ANESTHESIA", "麻醉科"), ("OPHTHALMOLOGY", "眼科"),
    ("CLIN_BONE_2", "骨二科"), ("CLIN_BONE_3", "骨三科"), ("SURG_2", "外二科"),
    ("SURG_4", "外四科"), ("INFECTIOUS", "感染科"), ("PEDIATRICS", "儿科"),
    ("ONCOLOGY_2", "肿瘤二科"), ("CLIN_NEURO_2", "内二科"), ("CLIN_NEURO_3", "内三科"),
    ("CLIN_NEURO_5", "内五科"), ("GASTRO", "消化内科"), ("CLIN_NEURO_1", "内一科"),
    ("CLIN_NEURO_4", "内四科"), ("RHEUMATOLOGY", "血液风湿科"), ("NEONATAL", "新生儿科"),
    ("ONCOLOGY_1", "肿瘤一科"), ("LAB", "检验科"), ("INTERVENTION", "介入科"),
    ("ULTRASOUND", "超声科"), ("RADIOLOGY", "放射科"), ("PATHOLOGY", "病理科"),
    ("TRANSFUSION", "输血科"), ("ICU", "重症医学科"), ("PAIN", "疼痛科"),
    ("DERMATOLOGY", "皮肤科"), ("EMERGENCY", "急诊医学科"), ("REHABILITATION", "康复医学科"),
    ("PSYCHIATRY", "精神科"), ("TCM", "中医科"), ("PREVENTION", "防保科"),
    ("LITHOTRIPSY", "碎石科"), ("ENDOSCOPY", "消化内镜"),
    ("MRI", "核磁共振室"), ("CT", "CT室"), ("CSSD", "消毒供应中心（CSSD）"),
    ("EEG", "脑电图室"), ("ECG", "心电图室"), ("RADIOTHERAPY", "放疗中心"),
    ("HEMODIALYSIS", "血透室"), ("HEALTH_MANAGEMENT", "健康管理中心"),
    ("BLOOD_BANK", "中心血库"), ("PHARMACY", "药学部"),
]

DEPARTMENTS = [
    {
        "code": code,
        "name": name,
        "short_name": name,
        "description": "天长市人民医院官网科室目录公开科室。医生资料以对应科室页面公开信息为准。",
        "source_url": "https://www.tcsyy.com/cms/c/keshijianjie.html",
    }
    for code, name in _DEPARTMENT_NAMES
]

for department in DEPARTMENTS:
    if department["code"] == "CLIN_NEURO_3":
        department.update(
            description=(
                "官网页面称神经内科，重点开展脑血管疾病、脑出血微创、神经介入及神经重症相关诊疗，"
                "并与神经外科、康复科开展多学科协作。"
            ),
            source_url=DEPARTMENT_SOURCE_URL,
        )
        break

DOCTORS = [
    {
        "source_id": "1020",
        "name": "李建军",
        "title": "副主任医师",
        "specialties": ["神经内科", "脑血管病", "脑血管介入", "脑出血微创术"],
        "introduction": (
            "内三科科主任，副主任医师。擅长脑血管病、肌病、脱髓鞘疾病、中枢神经系统感染及周围神经疾病诊治，"
            "擅长脑血管介入术、微创术，尤其擅长脑出血疾病的颅内血肿微创术。"
        ),
        "avatar_url": "https://www.tcsyy.com/uploads/20200807/08b8ddac84c559f91f7feed42f4fe37c.jpg",
        "profile_url": "https://www.tcsyy.com/cms/a/1020.html",
    },
    {
        "source_id": "1025",
        "name": "张建业",
        "title": "主治医师",
        "specialties": ["神经内科", "脑血管疾病", "眩晕", "头痛", "癫痫"],
        "introduction": (
            "神经内科主治医师。熟练掌握神经内科常见病、疑难病的诊治，"
            "擅长脑血管疾病的规范化防治及眩晕、运动障碍、痴呆、癫痫、头痛和中枢神经系统感染等疾病的诊治。"
        ),
        "avatar_url": "https://www.tcsyy.com/uploads/20200807/7cdd62ce621f8be5f14f680f031d37a1.jpg",
        "profile_url": "https://www.tcsyy.com/cms/a/1025.html",
    },
    {
        "source_id": "1023",
        "name": "刘梅",
        "title": "副主任医师",
        "specialties": ["缺血性脑血管病", "眩晕", "头痛", "认知功能障碍", "神经介入"],
        "introduction": (
            "神经内科副主任医师，硕士研究生。擅长缺血性脑血管、眩晕、头痛、认知功能障碍等诊治，"
            "熟练掌握脑血管造影、急诊颅内动脉取栓术及颈动脉、椎动脉和锁骨下动脉支架置入术等治疗操作。"
        ),
        "avatar_url": "https://www.tcsyy.com/uploads/20200807/96fc4a7cafdee6364100275ab6223704.jpg",
        "profile_url": "https://www.tcsyy.com/cms/a/1023.html",
    },
    {
        "source_id": "1021",
        "name": "罗涛",
        "title": "副主任医师",
        "specialties": ["急性脑血管病", "头痛", "头晕", "癫痫", "帕金森病", "痴呆"],
        "introduction": (
            "神经内科副主任医师。熟练掌握神经内科常见疾病的诊疗，"
            "擅长急性脑血管病、头痛、头晕、癫痫、帕金森病、痴呆、中枢系统炎症性疾病和神经肌肉疾病等诊治。"
        ),
        "avatar_url": "https://www.tcsyy.com/uploads/20200807/37abcce7ea7c46b263ebd25036cde9ec.jpg",
        "profile_url": "https://www.tcsyy.com/cms/a/1021.html",
    },
    {
        "source_id": "1022",
        "name": "钱改河",
        "title": "主任医师",
        "specialties": ["神经内科", "脑血管疾病", "运动障碍", "痴呆", "癫痫", "睡眠障碍"],
        "introduction": (
            "主任医师。擅长神经内科常见病和疑难病的诊治、脑血管疾病规范化防治，"
            "以及运动障碍、痴呆、癫痫、头痛、头晕、睡眠障碍和神经精神心理相关疾病的诊治。"
        ),
        "avatar_url": "https://www.tcsyy.com/uploads/20200807/5d602c5dfccd3a3752ebac2201d40884.jpg",
        "profile_url": "https://www.tcsyy.com/cms/a/1022.html",
    },
    {
        "source_id": "1024",
        "name": "杨彩云",
        "title": "主治医师",
        "specialties": ["缺血性脑血管病", "眩晕", "头痛", "认知功能障碍", "神经血管介入"],
        "introduction": (
            "神经内科主治医师。掌握缺血性脑血管、眩晕、头痛、认知功能障碍、中枢神经系统感染等常见病诊治，"
            "掌握脑血管造影、急诊颅内动脉取栓术等相关治疗操作。"
        ),
        "avatar_url": "https://www.tcsyy.com/uploads/20200807/a058896b4aa10dafe5329576c444bbd2.jpg",
        "profile_url": "https://www.tcsyy.com/cms/a/1024.html",
    },
    {
        "source_id": "1920",
        "name": "毛昌健",
        "title": "住院医师",
        "specialties": ["神经内科", "脑血管病", "周围神经病", "头痛"],
        "introduction": "神经内科住院医师。熟练掌握内科常见病、多发病的诊治，擅长脑血管病、周围神经病和各种头痛等疾病的诊治。",
        "avatar_url": "https://www.tcsyy.com/uploads/20250718/2801380cd4f6dd8e4a114c7fbb766b58.jpg",
        "profile_url": "https://www.tcsyy.com/cms/a/1920.html",
    },
    {
        "source_id": "1919",
        "name": "周春玉",
        "title": "住院医师",
        "specialties": ["神经内科", "脑血管病", "颅内感染", "周围神经病", "头痛"],
        "introduction": "神经内科住院医师。熟练掌握内科常见病，擅长脑血管病、颅内感染、周围神经病变和各种头痛等疾病的诊治。",
        "avatar_url": "https://www.tcsyy.com/uploads/20250718/805b8b481d3795dbd07ab7a32a43a607.jpg",
        "profile_url": "https://www.tcsyy.com/cms/a/1919.html",
    },
]
