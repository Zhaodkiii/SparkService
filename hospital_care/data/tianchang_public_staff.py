"""天长市中医院官网公开科室与专家数据快照。

来源：
- http://www.tcszyy.com/ks.html
- http://www.tcszyy.com/channels/103.html
- http://www.tcszyy.com/channels/104.html

抓取日期：2026-09-04。临床专家页公开 145 张卡片，按姓名去重后为 142 位人员；
重复人员保留全部科室关系。医技科室官网当前未公开专家卡片，因此不虚构人员。
仅保存官网公开的姓名、职称、诊室、擅长、头像和详情页，不保存手机号或证件信息。
"""

from __future__ import annotations

SOURCE_UPDATED_AT = "2026-09-04"
SOURCE_DEPARTMENT_URL = "http://www.tcszyy.com/ks.html"
SOURCE_CLINICAL_EXPERT_URL = "http://www.tcszyy.com/channels/103.html"
SOURCE_MEDTECH_EXPERT_URL = "http://www.tcszyy.com/channels/104.html"

# 官网同一人员可能同时出现在综合科室和专病门诊；以下规则只确定一个智能体的主科室，
# DoctorDepartmentMembership 仍保留官网公开的全部科室关系。
PRIMARY_DEPARTMENT_OVERRIDES = {
    "黄书谦": "CLIN_SMOKE",
    "吴大山": "CLIN_REHAB",
    "吴生保": "CLIN_ONCO",
}

# code, name, short_name, description, parent_code
DEPARTMENTS: list[tuple[str, str, str, str, str | None]] = [
    ('CLINICAL', '临床科室', '临床科室', '医院官网科室导航中的临床科室分类', None),
    ('CLIN_IM1', '内一科', '内一科', '综合内科，涵盖心脑血管、呼吸、内分泌等常见病和危急重症', 'CLINICAL'),
    ('CLIN_IM2', '内二科', '内二科', '综合内科，涵盖脾胃、肝胆、呼吸、神经及肾病诊疗', 'CLINICAL'),
    ('CLIN_SURG', '外科', '外科', '普通外科、肝胆胰、甲乳及腹腔镜等外科诊疗', 'CLINICAL'),
    ('CLIN_ORTH_NS', '骨伤脑外', '骨伤脑外', '骨伤、脊柱关节、神经外科和脑血管疾病诊疗', 'CLINICAL'),
    ('CLIN_ONCO', '肿瘤科', '肿瘤科', '肿瘤放疗、化疗、介入、靶向免疫及中医药综合治疗', 'CLINICAL'),
    ('CLIN_OBGYN', '妇产科', '妇产科', '围产保健、产科及妇科疾病诊疗', 'CLINICAL'),
    ('CLIN_PED', '儿科', '儿科', '儿童常见病、危急重症及新生儿诊疗', 'CLINICAL'),
    ('CLIN_EMS120', '120急救中心', '120急救', '院前急救与急危重症救治', 'CLINICAL'),
    ('CLIN_REHAB', '康复科', '康复科', '康复评定、运动治疗和功能训练', 'CLINICAL'),
    ('CLIN_ACU', '针灸理疗科', '针灸理疗', '针灸、推拿、理疗与中风康复', 'CLINICAL'),
    ('CLIN_EYE', '眼科', '眼科', '眼科常见病、眼底病及眼科手术', 'CLINICAL'),
    ('CLIN_ENT', '耳鼻咽喉科', '耳鼻咽喉', '耳鼻咽喉常见病、疑难病及手术治疗', 'CLINICAL'),
    ('CLIN_DENT', '口腔科', '口腔科', '牙体牙髓、修复、正畸与口腔外科', 'CLINICAL'),
    ('CLIN_DERM', '皮肤科', '皮肤科', '皮肤常见病、疑难病与激光治疗', 'CLINICAL'),
    ('CLIN_PROCT', '肛肠科', '肛肠科', '痔、瘘、裂及其他肛肠疾病诊疗', 'CLINICAL'),
    ('CLIN_ANDRO', '男科', '男科', '男性生殖与泌尿系统疾病诊疗', 'CLINICAL'),
    ('CLIN_SMOKE', '戒烟门诊', '戒烟门诊', '烟草依赖评估、戒烟干预与随访', 'CLINICAL'),
    ('CLIN_GERI', '老年医学科', '老年医学', '老年综合评估与老年常见病诊疗', 'CLINICAL'),
    ('MEDTECH', '医技科室', '医技科室', '医院官网科室导航中的医技科室分类', None),
    ('TECH_RAD', '放射科', '放射科', '普通放射检查与影像诊断', 'MEDTECH'),
    ('TECH_CT', 'CT室', 'CT室', 'CT检查与影像诊断', 'MEDTECH'),
    ('TECH_MRI', '磁共振室', '磁共振', '磁共振检查与影像诊断', 'MEDTECH'),
    ('TECH_US', 'B超室', 'B超室', '超声检查与诊断', 'MEDTECH'),
    ('TECH_ECG', '心电图室', '心电图', '心电图检查与诊断', 'MEDTECH'),
    ('TECH_DIALYSIS', '血液净化中心', '血液净化', '血液透析与血液净化治疗', 'MEDTECH'),
    ('TECH_LITHO', '碎石中心', '碎石中心', '泌尿系结石体外碎石治疗', 'MEDTECH'),
    ('TECH_PHARM', '药剂科', '药剂科', '药品供应、调剂与临床药学服务', 'MEDTECH'),
    ('TECH_PATH', '病理科', '病理科', '组织病理、细胞病理与术中病理诊断', 'MEDTECH'),
    ('TECH_LAB', '检验科', '检验科', '临床检验与实验室诊断', 'MEDTECH'),
]

# 每行：department_code<TAB>name<TAB>title<TAB>room<TAB>specialty<TAB>avatar_url<TAB>profile_url
_PUBLIC_DOCTOR_CARDS_TSV = """\
CLIN_IM1	周义忠	副主任中医师	2055	咳喘、中风、心悸等心、脑、肺部疾患等内科疾病的中西医结合诊治。	http://www.tcszyy.com/upload/images/2025/3/271684637.jpg	http://www.tcszyy.com/contents/155/206.html
CLIN_IM1	张晓东	副主任医师	2057	电子支气管镜检查治疗、胸腔闭式引流术、呼吸机（有创、无创）使用等技术操作，对呼吸专业疑难病诊治及急重症疾病抢救有一定的经验。	http://www.tcszyy.com/upload/images/2025/3/27161623404.jpg	http://www.tcszyy.com/contents/155/185.html
CLIN_IM1	戴雪梅	副主任中医师	2026	心脑血管疾病的中西医结合诊治。	http://www.tcszyy.com/upload/images/2025/3/27161740255.jpg	http://www.tcszyy.com/contents/155/202.html
CLIN_IM1	周道春	副主任中医师	2003	擅长中医中药治疗慢性咳嗽、慢支、慢阻肺、哮喘等疾病。	http://www.tcszyy.com/upload/images/2025/3/2716181855.jpg	http://www.tcszyy.com/contents/155/199.html
CLIN_IM1	魏斌	副主任医师	2号楼2楼重症医学科	致力并擅长于对各种急危重症疾病的及时、准确诊断，快速、高效规范救治，客观、量化、规范评估病情与衡量治疗效果。	http://www.tcszyy.com/upload/images/2025/3/27162144619.jpg	http://www.tcszyy.com/contents/155/184.html
CLIN_IM1	马莉莉	主治医师	3号楼14层内一科	糖尿病、甲状腺疾病、心脑血管病的诊治。	http://www.tcszyy.com/upload/images/2025/3/27162417768.jpg	http://www.tcszyy.com/contents/155/197.html
CLIN_IM1	吴秋军	副主任医师	2036	心血管疾病的诊治及介入治疗。	http://www.tcszyy.com/upload/images/2025/3/2716287579.jpg	http://www.tcszyy.com/contents/155/173.html
CLIN_IM1	黄书谦	副主任中医师	2019	对呼吸系统常见病、多发病的诊治具有丰富的临床经验，擅长中西医结合方法治疗肺癌、改善晚期肿瘤患者的生存质量、风湿病、糖尿病、消化病及妇科病等中医治疗。	http://www.tcszyy.com/upload/images/2025/3/281039655.jpg	http://www.tcszyy.com/contents/155/190.html
CLIN_IM1	张万林	副主任医师	2037	肿瘤放化疗、介入治疗等综合治疗。	http://www.tcszyy.com/upload/images/2025/3/2716396538.jpg	http://www.tcszyy.com/contents/155/251.html
CLIN_IM1	岳正山	副主任医师	2036	内科常见病及疑难病症的诊治，尤其是心血管疾病的诊断和急危重症的救治。	http://www.tcszyy.com/upload/images/2025/3/2716402823.jpg	http://www.tcszyy.com/contents/155/191.html
CLIN_IM1	洪守祥	副主任医师	2055	内科常见病多发病诊治，尤其是心血管疾病的诊治。	http://www.tcszyy.com/upload/images/2025/3/27164225845.jpg	http://www.tcszyy.com/contents/155/183.html
CLIN_IM1	王丽兵	主任医师	2056	擅长神经内科、呼吸内科疾病及相应疑难危重病的诊治。	http://www.tcszyy.com/upload/images/2025/3/2716455880.jpg	http://www.tcszyy.com/contents/155/201.html
CLIN_IM1	张贵荣	副主任医师	2008	擅长中西医结合治疗呼吸系统、消化系统疾病及内科常见病。	http://www.tcszyy.com/upload/images/2025/3/27164742794.jpg	http://www.tcszyy.com/contents/155/178.html
CLIN_IM1	徐广东	主治医师	2055	呼吸科、消化科、心血管等常见病的中西医结合诊治。	http://www.tcszyy.com/upload/images/2025/3/27165040147.jpg	http://www.tcszyy.com/contents/155/1852.html
CLIN_IM1	陈晓东	主治医师	2号楼2楼重症医学科	对各种急慢性呼吸衰竭、脓毒症、多脏器功能障碍、中毒、休克、严重创伤、复合伤、多发伤及大手术后监护治疗等危重症抢救治疗、监测有较丰富的临床经验。	http://www.tcszyy.com/upload/images/2025/3/27165350127.jpg	http://www.tcszyy.com/contents/155/1844.html
CLIN_IM1	刘咏民	主治医师	2号楼2楼重症医学科	一直注重重症医学的规范化诊治、抢救及评估。	http://www.tcszyy.com/upload/images/2025/3/27165586.jpg	http://www.tcszyy.com/contents/155/1845.html
CLIN_IM1	陈金鑫	主治医师	2号楼2楼重症医学科	重视重症医学的规范化诊治及抢救，对重症肺炎、呼吸衰竭、脓毒症休克、多脏器功能不全、急性重症胰腺炎、多发伤等危重病有较丰富的临床经验。	http://www.tcszyy.com/upload/images/2025/3/27165649606.jpg	http://www.tcszyy.com/contents/155/1846.html
CLIN_IM1	陈高俊	主治医师	2056	神经系统常见病的诊断及治疗，特别是脑血管病、眩晕、癫痫、帕金森病，对神经内科危重症、少见病、疑难杂症救治有丰富的经验。	http://www.tcszyy.com/upload/images/2025/3/27165751302.jpg	http://www.tcszyy.com/contents/155/1848.html
CLIN_IM1	张志浩	主治医师	2055	内分泌、心血管系统等疾患的中西医结合诊治。	http://www.tcszyy.com/upload/images/2025/3/27165924837.jpg	http://www.tcszyy.com/contents/155/1849.html
CLIN_IM1	李枢娟	主治医师	2036	内科常见病多发病的中西医结合诊治，尤其是心血管系统疾病。	http://www.tcszyy.com/upload/images/2025/3/2717046590.jpg	http://www.tcszyy.com/contents/155/1851.html
CLIN_IM2	何镔	主任中医师	2008	治疗萎缩性胃炎、胃癌前期病变、炎症性肠病、消化性溃疡、肝胆病、消化道肿瘤、高血压病、妇科疾病、风湿病等各科疑难杂症。	http://www.tcszyy.com/upload/images/2025/3/271784962.jpg	http://www.tcszyy.com/contents/27/212.html
CLIN_IM2	郑曰俊	副主任中医师	2005	中医内科肝胆脾胃疾病及咳喘、胸痹、腰腿痛、头痛、眩晕等症的诊治。	http://www.tcszyy.com/upload/images/2025/3/27171215577.jpg	http://www.tcszyy.com/contents/27/211.html
CLIN_IM2	万延梅	副主任医师	2033	内科常见病多发病的诊治，尤擅长心脑血管疾病、甲状腺和风湿免疫性疾病的治疗。	http://www.tcszyy.com/upload/images/2025/3/27171328356.jpg	http://www.tcszyy.com/contents/27/207.html
CLIN_IM2	张鸿飞	副主任中医师	2009	治内科疑难杂症，验方治疗头痛、偏头痛、颈椎病、腰椎病等病症，对脾胃病诊疗有独到之法。	http://www.tcszyy.com/upload/images/2025/3/27171436566.jpg	http://www.tcszyy.com/contents/27/205.html
CLIN_IM2	周连宽	副主任中医师	2006	擅长治疗咳喘、中风、脾胃病、肝胆病及内科杂病。	http://www.tcszyy.com/upload/images/2025/3/27171551228.jpg	http://www.tcszyy.com/contents/27/204.html
CLIN_IM2	高明友	副主任中医师	2056	慢性肝胆病、胰腺炎、肝硬化腹水、肝纤维化及脾胃疾病的中西医结合诊治。	http://www.tcszyy.com/upload/images/2025/3/27171841103.jpg	http://www.tcszyy.com/contents/27/203.html
CLIN_IM2	肖昌庆	副主任中医师	2002	糖尿病、甲状腺、代谢综合征等内分泌疾病的中西医结合诊治。	http://www.tcszyy.com/upload/images/2025/3/27172346866.jpg	http://www.tcszyy.com/contents/27/200.html
CLIN_IM2	朱元平	副主任中医师	2031	于内科常见病多发病的中西医结合诊治及抢救治疗。	http://www.tcszyy.com/upload/images/2025/3/2885255426.jpg	http://www.tcszyy.com/contents/27/198.html
CLIN_IM2	朱俊玲	主任中医师	2056	内科常见病诊治及神经系统疾病的诊断和治疗，如：头痛、眩晕、脑梗塞，脑出血及癫痫，脑炎、帕金森病等。	http://www.tcszyy.com/upload/images/2025/3/289800.jpg	http://www.tcszyy.com/contents/27/196.html
CLIN_IM2	潘军	副主任中医师	2058	中医治疗内科杂病，特别是慢性肾炎、蛋白尿、血液透析相关并发症、消化性溃疡、功能性胃肠病、反流性胃炎、萎缩性胃炎等消化科肾科常见疾病的中医及中西医配合治疗。	http://www.tcszyy.com/upload/images/2025/3/289233098.jpg	http://www.tcszyy.com/contents/27/195.html
CLIN_IM2	龚晓林	主治中医师	2013	从事内妇科疾病诊治及冷冻等多种美容治疗。	http://www.tcszyy.com/upload/images/2025/3/2892517920.jpg	http://www.tcszyy.com/contents/27/194.html
CLIN_IM2	李爱北	主治中医师	2012	治慢性肾炎，慢性肝炎，慢性胃炎及妇科经、带诸病。	http://www.tcszyy.com/upload/images/2025/3/2892629516.jpg	http://www.tcszyy.com/contents/27/193.html
CLIN_IM2	吴永国	中医师	2027	治疗多种疑难杂症，尤对中医药治疗恶性肿瘤有所研究。	http://www.tcszyy.com/upload/images/2025/3/2892756304.jpg	http://www.tcszyy.com/contents/27/192.html
CLIN_IM2	陶泽红	副主任中医师	3010	于妇科不孕不育，更年期综合症，乳腺病、月经病、宫颈疾病、妇科类症性疾病及内科常见病的诊治。	http://www.tcszyy.com/upload/images/2025/3/2892910108.jpg	http://www.tcszyy.com/contents/27/189.html
CLIN_IM2	程继明	副主任中医师	2021	消化系统疾患的中西医结合诊治和胃肠道息肉及消化道早癌的治疗，尤其是胃肠镜检查操作治疗。	http://www.tcszyy.com/upload/images/2025/3/2893025318.jpg	http://www.tcszyy.com/contents/27/188.html
CLIN_IM2	曹正龙	副主任中医师	2022	消化系统常见病的中西医结合诊治及不明原因消化道出血等疑难病诊治，尤其是胃肠镜诊查治疗和消化道早癌及癌前病变内镜检出。	http://www.tcszyy.com/upload/images/2025/3/2893138108.jpg	http://www.tcszyy.com/contents/27/187.html
CLIN_IM2	宣建宗	副主任医师	2058	中西医结合治疗蛋白尿，血尿，尿路感染，慢性肾炎，肾病综合征，慢性肾衰竭，糖尿病肾病，狼疮性肾病等原发和继发性肾脏疾病，以及血液净化相关疾病。	http://www.tcszyy.com/upload/images/2025/3/2893250330.jpg	http://www.tcszyy.com/contents/27/186.html
CLIN_IM2	林莉	主治医师	2058	诊治慢性肾小球肾炎、泌尿系感染、血尿、蛋白尿等疾病筛查，以及糖尿病肾病、尿毒症的透析治疗、掌握血液灌流，血液透析滤过技术, 能操作颈内、股静脉置管及动静脉内瘘吻合术。处理透析中的急慢性并发症。	http://www.tcszyy.com/upload/images/2025/3/289341481.jpg	http://www.tcszyy.com/contents/27/182.html
CLIN_IM2	詹士宝	副主任医师	2056	胃肠疾病及肝胆胰疾病的诊治，胃镜、结肠镜等消化内镜的诊治工作。	http://www.tcszyy.com/upload/images/2025/3/289351889.jpg	http://www.tcszyy.com/contents/27/181.html
CLIN_IM2	丁仁华	副主任中医师	2033	中西医结合诊治内科常见病多发病	http://www.tcszyy.com/upload/images/2025/3/289394191.jpg	http://www.tcszyy.com/contents/27/179.html
CLIN_IM2	戴书陈	副主任中医师	2008	脾胃病、肝胆病、风湿内分泌等内科常见病的诊治。	http://www.tcszyy.com/upload/images/2025/3/2894156910.jpg	http://www.tcszyy.com/contents/27/176.html
CLIN_IM2	潘寅甲	主治中医师	2020	中西医结合诊治内科、妇科、皮肤科等常见病多发病。	http://www.tcszyy.com/upload/images/2025/3/289439999.jpg	http://www.tcszyy.com/contents/27/175.html
CLIN_IM2	钱冬梅	副主任中医师	2002	糖尿病及其各种并发症等内分泌疾患的中西医结合治疗。	http://www.tcszyy.com/upload/images/2025/3/2894421332.jpg	http://www.tcszyy.com/contents/27/174.html
CLIN_SURG	刘剑超	副主任医师	3050	肝胆胰疾病、肿瘤的诊治手术、腹腔镜手术。	http://www.tcszyy.com/upload/images/2025/3/2894549469.jpg	http://www.tcszyy.com/contents/51/232.html
CLIN_SURG	王鹤林	副主任医师	3063	食管、胃、结肠、直肠疾病内镜检查诊断和内镜下手术治疗，以及外科常见病多发病的诊治。	http://www.tcszyy.com/upload/images/2025/3/2894725914.jpg	http://www.tcszyy.com/contents/51/228.html
CLIN_SURG	陈新民	主任医师	3052	肝胆胰、甲状腺乳腺、心胸外科等疾患的常规手术及腔镜手术治疗，尤其是急危重症及疑难病例的诊治。	http://www.tcszyy.com/upload/images/2025/3/289493411.jpg	http://www.tcszyy.com/contents/51/231.html
CLIN_SURG	何如恒	副主任中医师	2053	外科常见病多发病诊治，尤其甲状腺、乳腺、消化道肿瘤、肝胆创伤外科手术治疗。	http://www.tcszyy.com/upload/images/2025/3/2895240862.jpg	http://www.tcszyy.com/contents/51/230.html
CLIN_SURG	刘春雨	主治医师	3号楼8层外二科	普外科常见病、多发病及疑难病诊治,尤其甲状腺、乳腺、消化道肿瘤、肝胆创伤外科。	http://www.tcszyy.com/upload/images/2025/3/2895339492.jpg	http://www.tcszyy.com/contents/51/229.html
CLIN_SURG	丁兆云	主治医师	3066	乳房病外科，腰腿痛诊治。	http://www.tcszyy.com/upload/images/2025/3/2895558260.jpg	http://www.tcszyy.com/contents/51/227.html
CLIN_SURG	蒋学才	副主任医师	3062	外科常见病、多发病治疗和腹腔镜手术。	http://www.tcszyy.com/upload/images/2025/3/2895657857.jpg	http://www.tcszyy.com/contents/51/226.html
CLIN_SURG	宣丁元	副主任医师	3052	普外科常见病多发病的临床诊断和手术治疗，对普外科危急重症诊治具有一定临床经验。	http://www.tcszyy.com/upload/images/2025/3/2895822621.jpg	http://www.tcszyy.com/contents/51/225.html
CLIN_SURG	虞昌文	主任医师	3035	治疗前列腺疾病、泌尿系结石、女性尿失禁及泌尿系肿瘤	http://www.tcszyy.com/upload/images/2025/3/281037997.jpg	http://www.tcszyy.com/contents/51/224.html
CLIN_SURG	岑付元	副主任医师	3052	外科常见病多发病诊治和急危重症及疑难病例的诊治，对腹腔镜微创手术有丰富的临床经验。	http://www.tcszyy.com/upload/images/2025/3/2810455749.jpg	http://www.tcszyy.com/contents/51/223.html
CLIN_SURG	管玉彬	主治医师	3033	泌尿外科常见病及疑难病诊治，以及外科常见病多发病的诊治。	http://www.tcszyy.com/upload/images/2025/3/2810613407.jpg	http://www.tcszyy.com/contents/51/222.html
CLIN_SURG	张曙光	主治医师	3053	普外科常见病多发病及疑难病诊治。	http://www.tcszyy.com/upload/images/2025/3/2810714795.jpg	http://www.tcszyy.com/contents/51/221.html
CLIN_SURG	胡世成	副主任医师	3035	泌尿外科及普外科常见病多发病诊治，尤其是泌尿外科疾病的微创手术治疗。	http://www.tcszyy.com/upload/images/2025/3/28101335787.jpg	http://www.tcszyy.com/contents/51/220.html
CLIN_SURG	徐晓辉	副主任医师	3062	普外科常见病多发病诊治和外科疾病各类小切口微创手术及腹腔镜技术。	http://www.tcszyy.com/upload/images/2025/3/28101455732.jpg	http://www.tcszyy.com/contents/51/219.html
CLIN_SURG	陆杨超	副主任医师	3062	熟练掌握普外科常见病多发病的诊治，常规开展腹腔镜下阑尾、胆囊切除术。	http://www.tcszyy.com/upload/images/2025/3/2810173235.jpg	http://www.tcszyy.com/contents/51/218.html
CLIN_ORTH_NS	徐荣林	副主任医师	3060	骨病、骨伤、神经外科、颈肩腰腿痛及疑难杂症的诊疗。	http://www.tcszyy.com/upload/images/2025/3/28104152220.jpg	http://www.tcszyy.com/contents/24/172.html
CLIN_ORTH_NS	王洪海	主任医师	3065	运用中西医结合治疗骨伤科疑难病症，尤其骨折创伤、脊柱疾患、骨质疏松症。	http://www.tcszyy.com/upload/images/2025/3/28104251550.jpg	http://www.tcszyy.com/contents/24/171.html
CLIN_ORTH_NS	周连发	主任医师	3051	长脑血管病（出血性和缺血性）的手术和微创介入（脑动脉瘤栓塞、脑血管狭窄、急性脑梗塞机械取栓）治疗。	http://www.tcszyy.com/upload/images/2025/3/281044590.jpg	http://www.tcszyy.com/contents/24/170.html
CLIN_ORTH_NS	凌长华	主治医师	3061	骨伤科常见病多发病及疑难杂症的中西医结合诊治，尤擅长骨盆、脊柱、四肢骨折、关节等方面骨科复杂手术。	http://www.tcszyy.com/upload/images/2025/3/2810455646.jpg	http://www.tcszyy.com/contents/24/169.html
CLIN_ORTH_NS	李加松	主治中医师	3055	骨伤科、脑外科常见病多发病治疗及疑难病症处理。	http://www.tcszyy.com/upload/images/2025/3/281046544.jpg	http://www.tcszyy.com/contents/24/168.html
CLIN_ORTH_NS	杨树明	副主任中医师	3061	骨伤科常见病多发病的诊治和骨盆、脊柱、四肢骨折、关节等方面骨科手术治疗。	http://www.tcszyy.com/upload/images/2025/3/28104743244.jpg	http://www.tcszyy.com/contents/24/167.html
CLIN_ORTH_NS	李明生	副主任医师	3055	脑外科骨伤科常见病多发病诊治。	http://www.tcszyy.com/upload/images/2025/3/28104853632.jpg	http://www.tcszyy.com/contents/24/166.html
CLIN_ORTH_NS	张金昌	主治医师	3061	骨伤科常见病多发病的诊治和骨盆、脊柱、四肢骨折、关节等方面骨科手术治疗。	http://www.tcszyy.com/upload/images/2025/3/28104956532.jpg	http://www.tcszyy.com/contents/24/165.html
CLIN_ORTH_NS	林道云	副主任医师	3055	脑外伤、脑肿瘤、高血压脑出血、急性脑梗死等常见病的诊疗以及脑血管疾病介入微创治疗等。	http://www.tcszyy.com/upload/images/2025/3/28105222577.jpg	http://www.tcszyy.com/contents/24/164.html
CLIN_ORTH_NS	薛晓强	主治医师	3061	骨伤科常见病多发病的诊治和骨盆、脊柱、四肢骨折、关节等方面骨科手术治疗。	http://www.tcszyy.com/upload/images/2025/3/28105326212.jpg	http://www.tcszyy.com/contents/24/163.html
CLIN_ORTH_NS	陈开军	副主任医师	3061	四肢创伤骨折、手足病损的诊治，关节镜微创治疗肩膝关节疼痛。	http://www.tcszyy.com/upload/images/2025/3/28153058650.jpg	http://www.tcszyy.com/contents/24/162.html
CLIN_ORTH_NS	张寒	副主任医师	3061	骨科常见病多发病诊治，尤擅长手外伤的治疗、手部血管、神经、肌腱损伤的修复等。	http://www.tcszyy.com/upload/images/2025/3/2810551238.jpg	http://www.tcszyy.com/contents/24/161.html
CLIN_ORTH_NS	程永胜	副主任中医师	3061	于骨伤科常见病多发病诊治手外伤的治疗。	http://www.tcszyy.com/upload/images/2025/3/28105614846.jpg	http://www.tcszyy.com/contents/24/160.html
CLIN_ORTH_NS	吴大山	副主任治疗师	2099	中风偏瘫及骨关节功能障碍等疾病的综合康复治疗。	http://www.tcszyy.com/upload/images/2025/3/28105723857.jpg	http://www.tcszyy.com/contents/24/1515.html
CLIN_ONCO	李婷婷	主治中医师	2038	肿瘤科常见病多发病的综合治疗，尤擅长常见肿瘤的放射治疗和中医中药治疗。	http://www.tcszyy.com/upload/images/2025/3/28144357843.jpg	http://www.tcszyy.com/contents/147/2559.html
CLIN_ONCO	金星宇	主治中医师	2038	肿瘤科常见病多发病的治疗，尤其擅长肿瘤科和血管外科常见病的介入治疗。	http://www.tcszyy.com/upload/images/2025/3/28144144905.jpg	http://www.tcszyy.com/contents/147/2558.html
CLIN_ONCO	景文冬	主治医师	2038	肿瘤内科常见病多发病的诊治及肿瘤介入治疗。	http://www.tcszyy.com/upload/images/2025/3/28144029921.jpg	http://www.tcszyy.com/contents/147/2557.html
CLIN_ONCO	冯天明	副主任中医师	2029	肿瘤的放化疗、靶向免疫和中医药综合治疗，以及肿瘤疑难杂症的诊治和中医内科常见病多发病的诊疗。	http://www.tcszyy.com/upload/images/2025/3/28105932642.jpg	http://www.tcszyy.com/contents/147/257.html
CLIN_ONCO	查镜娟	副主任医师	2023	各种常见多发肿瘤和血液病的诊治，尤其是血液肿瘤和妇科肿瘤的放化疗。	http://www.tcszyy.com/upload/images/2025/3/2811327881.jpg	http://www.tcszyy.com/contents/147/256.html
CLIN_ONCO	吴生保	副主任中医师	2023	肿瘤疾病的诊治，放疗、化疗及中医药综合治疗，以及老年疾病的中医药综合治疗。	http://www.tcszyy.com/upload/images/2025/3/2811436746.jpg	http://www.tcszyy.com/contents/147/255.html
CLIN_ONCO	冯吉林	副主任中医师	2037	食管癌、胃癌、肺癌、乳腺癌等常见肿瘤的诊疗。	http://www.tcszyy.com/upload/images/2025/3/2811556477.jpg	http://www.tcszyy.com/contents/147/254.html
CLIN_ONCO	焦克	副主任医师	2023	常见肿瘤的诊断、鉴别诊断及治疗，尤其擅长肿瘤放化疗、靶向免疫等综合治疗。	http://www.tcszyy.com/upload/images/2025/3/28142235330.jpg	http://www.tcszyy.com/contents/147/253.html
CLIN_ONCO	郑晓霆	副主任医师	2035	内科常见病多发病的诊治及血管非血管介入手术治疗。	http://www.tcszyy.com/upload/images/2025/3/28143454308.jpg	http://www.tcszyy.com/contents/147/252.html
CLIN_ONCO	胡小莲	副主任中医师	2037	临床常见恶性肿瘤的放疗、化疗、免疫等肿瘤综合治疗。	http://www.tcszyy.com/upload/images/2025/3/2814365176.jpg	http://www.tcszyy.com/contents/147/250.html
CLIN_ONCO	时广伟	主治中医师	2038	恶性肿瘤的中西医结合治疗，尤其是食管癌、胃癌、结直肠癌等消化系统恶性肿瘤的诊治。	http://www.tcszyy.com/upload/images/2025/3/28143715302.jpg	http://www.tcszyy.com/contents/147/249.html
CLIN_ONCO	侯占国	主治医师	2038	结直肠癌、胃癌、食管癌、肺癌等常见肿瘤治疗。	http://www.tcszyy.com/upload/images/2025/3/28143822179.jpg	http://www.tcszyy.com/contents/147/248.html
CLIN_ONCO	阮鹏飞	主治医师	2023	常见肿瘤科常见病多发病的诊治。	http://www.tcszyy.com/upload/images/2025/3/28143926771.jpg	http://www.tcszyy.com/contents/147/247.html
CLIN_OBGYN	赵树娟	主治医师	3009	围产期保健，妇产科常见病多发病的诊治	http://www.tcszyy.com/upload/images/2025/3/2815417899.jpg	http://www.tcszyy.com/contents/21/2562.html
CLIN_OBGYN	龚新玲	主治医师	3009	围产期保健，妇产科常见病多发病的诊治和妇科产科常规手术的开展。	http://www.tcszyy.com/upload/images/2025/7/10173730751.jpg	http://www.tcszyy.com/contents/21/2561.html
CLIN_OBGYN	叶爱华	主任医师	3009	产科常规手术开展和妇科良恶性肿瘤手术治疗，尤擅长产科危重病人的诊治。	http://www.tcszyy.com/upload/images/2025/3/28144853483.jpg	http://www.tcszyy.com/contents/21/148.html
CLIN_OBGYN	陈士芳	主治医师	3012	治疗妇产科常见病、多发病及疑难杂症的诊治和妇科产科常规手术的开展。	http://www.tcszyy.com/upload/images/2025/3/28144956387.jpg	http://www.tcszyy.com/contents/21/147.html
CLIN_OBGYN	茆红梅	主治中医师	3011	乳腺疾病和妇科疾病的中西医结合综合治疗。	http://www.tcszyy.com/upload/images/2025/3/281451477.jpg	http://www.tcszyy.com/contents/21/146.html
CLIN_OBGYN	曹为英	副主任医师	3009	围产期保健，产科危重病人的诊治，妇产科常见病多发病的诊治和妇科产科常规手术的开展。	http://www.tcszyy.com/upload/images/2025/3/28145240651.jpg	http://www.tcszyy.com/contents/21/145.html
CLIN_OBGYN	江燕	副主任医师	3009	围产期保健，产科危重病人的诊治，妇科常见疾病及盆腔肿瘤的诊治等。	http://www.tcszyy.com/upload/images/2025/3/28145344857.jpg	http://www.tcszyy.com/contents/21/144.html
CLIN_OBGYN	张珍香	主治医师	3009	妇产科常见病多发病的诊断与治疗及妇科产科常规手术的开展。	http://www.tcszyy.com/upload/images/2025/3/28145438307.jpg	http://www.tcszyy.com/contents/21/143.html
CLIN_OBGYN	肖淑琴	主治医师	3号楼4层妇产科	妇产科常见病、多发病治疗。	http://www.tcszyy.com/upload/images/2025/3/28145633956.jpg	http://www.tcszyy.com/contents/21/142.html
CLIN_OBGYN	王春香	主治医师	3009	围产期保健，产科危重病人的诊治，妇产科常见病多发病及疑难杂症的诊治和妇科产科常规手术的开展。	http://www.tcszyy.com/upload/images/2025/3/28145819511.jpg	http://www.tcszyy.com/contents/21/141.html
CLIN_OBGYN	陈辰	副主任医师	3009	围产期保健，妇产科常见病多发病的诊治和妇科良恶性肿瘤手术治疗。	http://www.tcszyy.com/upload/images/2025/3/28145914163.jpg	http://www.tcszyy.com/contents/21/140.html
CLIN_OBGYN	叶仁丽	副主任医师	3009	围产期保健，妇产科常见病多发病的诊治和妇科产科常规手术的开展。	http://www.tcszyy.com/upload/images/2025/3/2815129210.jpg	http://www.tcszyy.com/contents/21/27.html
CLIN_PED	夏维国	副主任医师	108	儿科的常见病多发病、疑难杂病及危急重症的诊治。	http://www.tcszyy.com/upload/images/2025/3/28153222341.jpg	http://www.tcszyy.com/contents/30/134.html
CLIN_PED	王其斌	主任医师	3号楼五层儿科	儿科危重症急救和疑难杂症的诊治，尤擅长新生儿各种危急重症救治。	http://www.tcszyy.com/upload/images/2025/3/28153318712.jpg	http://www.tcszyy.com/contents/30/133.html
CLIN_PED	朱培林	主治中医师	103	于运用中西医结合方法诊治儿科常见病多发病。	http://www.tcszyy.com/upload/images/2025/3/28153430150.jpg	http://www.tcszyy.com/contents/30/130.html
CLIN_PED	姚红	副主任医师	107	儿科呼吸、消化、感染性疾病及儿童生长发育、营养性疾病的诊治。	http://www.tcszyy.com/upload/images/2025/3/28153520537.jpg	http://www.tcszyy.com/contents/30/132.html
CLIN_PED	操芳琴	副主任医师	3号楼五层儿科	新生儿及儿科呼吸系统、消化系统、神经系统等常见病及多发病的诊断和治疗。	http://www.tcszyy.com/upload/images/2025/3/28153610446.jpg	http://www.tcszyy.com/contents/30/129.html
CLIN_PED	周进	主治医师	3号楼五层儿科	儿科呼吸系统、消化系统等常见病、多发病的诊断和治疗。	http://www.tcszyy.com/upload/images/2025/3/28153746868.jpg	http://www.tcszyy.com/contents/30/128.html
CLIN_PED	朱轩	主治医师	3号楼五层儿科	儿科呼吸系统、消化系统等常见病、多发病的诊断和治疗。	http://www.tcszyy.com/upload/images/2025/3/28153845483.jpg	http://www.tcszyy.com/contents/30/126.html
CLIN_PED	刘桂明	主治中医师	102	小儿反复呼吸道感染、过敏性咳嗽、腹泻、脾虚积食、厌食、便秘、自汗、腺样体肥大等常见病多发病中西医结合治疗。	http://www.tcszyy.com/upload/images/2025/3/28153939202.jpg	http://www.tcszyy.com/contents/30/125.html
CLIN_EMS120	瞿庆宏	主治中医师	120急救中心	常见病、多发病及部分疑难病中西医结合诊治，和急危重症的急诊急救。	http://www.tcszyy.com/upload/images/2025/3/2893627773.jpg	http://www.tcszyy.com/contents/152/180.html
CLIN_EMS120	吴生保	副主任中医师	2023	肿瘤疾病的诊治，放疗、化疗及中医药综合治疗，以及老年疾病的中医药综合治疗。	http://www.tcszyy.com/upload/images/2025/3/2811436746.jpg	http://www.tcszyy.com/contents/152/2555.html
CLIN_REHAB	叶飞	主治中医师	3031	于颈肩腰腿痛、带状疱疹、三叉神经痛及各种急慢性疼痛的特色治疗，从事针灸理疗、小针刀治疗、神经阻滞治疗及微创治疗。	http://www.tcszyy.com/upload/images/2025/3/318385198.jpg	http://www.tcszyy.com/contents/158/2565.html
CLIN_REHAB	吴大山	副主任治疗师	2099	中风偏瘫及骨关节功能障碍等疾病的综合康复治疗。	http://www.tcszyy.com/upload/images/2025/3/318378176.jpg	http://www.tcszyy.com/contents/158/2564.html
CLIN_REHAB	朱先明	副主任医师	2099	风及骨关节功能障碍康复，颈椎病、腰椎间盘突出症等病的诊断与治疗。	http://www.tcszyy.com/upload/images/2025/3/3183548312.jpg	http://www.tcszyy.com/contents/158/2563.html
CLIN_ACU	刘世华	副主任医师	针灸理疗科	面瘫、颈椎病、腰椎间盘突出等常见疾病的诊治及冬病夏治、针灸减肥、中风康复等特色治疗。	http://www.tcszyy.com/upload/images/2025/3/3184151323.jpg	http://www.tcszyy.com/contents/45/245.html
CLIN_ACU	王丽	主治中医师	针灸理疗科	颈椎病、腰椎间盘突出症、中风后遗症、面瘫、针灸减肥、冬病夏治等常见病、多发病及疑难杂证的诊治。	http://www.tcszyy.com/upload/images/2025/3/318424788.jpg	http://www.tcszyy.com/contents/45/244.html
CLIN_ACU	张顶慰	副主任医师	针灸理疗科	颈肩腰腿痛、急性腰扭伤、落枕、面瘫等疾患和中风后遗症的康复治疗等措施，疗效显著。	http://www.tcszyy.com/upload/images/2025/3/3184323540.jpg	http://www.tcszyy.com/contents/45/243.html
CLIN_ACU	曹丽丽	主治中医师	111、112	小儿感冒、斜颈、腹泻、脑瘫等儿科常见病的针灸推拿治疗。	http://www.tcszyy.com/upload/images/2025/3/3184418287.jpg	http://www.tcszyy.com/contents/45/242.html
CLIN_ACU	柏茂森	主治中医师	针灸理疗科	颈肩腰腿痛及中风康复的手法治疗。	http://www.tcszyy.com/upload/images/2025/3/3184532631.jpg	http://www.tcszyy.com/contents/45/241.html
CLIN_ACU	张瑶	主治中医师	2号楼2层康复科	颈椎病、腰椎间盘突出症、骨性关节炎、中风后遗症等疾病的特色治疗。	http://www.tcszyy.com/upload/images/2025/3/318466328.jpg	http://www.tcszyy.com/contents/45/240.html
CLIN_EYE	刘群	主治中医师	3119	眼表疾病和眼底疾病的诊断与治疗，眼部整形和美容各类手术：双眼皮手术，眼袋整复术，提眉术等。	http://www.tcszyy.com/upload/images/2025/3/319528358.jpg	http://www.tcszyy.com/contents/33/238.html
CLIN_EYE	李晓峰	副主任中医师	3121	白内障、青光眼、眼外伤的手术治疗，年均白内障超声乳化手术近500例，星期一全天门诊。	http://www.tcszyy.com/upload/images/2025/3/319639189.jpg	http://www.tcszyy.com/contents/33/236.html
CLIN_EYE	宛月	副主任医师	3122	儿童近视防控、散瞳验光、斜弱视等检查，翼状胬肉、倒睫、白内障、青光眼、上睑下垂等手术治疗。	http://www.tcszyy.com/upload/images/2025/3/3198639.jpg	http://www.tcszyy.com/contents/33/237.html
CLIN_EYE	张金铃	主治中医师	3120	葡萄膜炎及眼底疾病的诊治，如老年性黄斑变性，视网膜血管病变，糖尿病性视网膜病变等。对外眼手术及玻璃体腔内注射术拥有丰富的临床经验。	http://www.tcszyy.com/upload/images/2025/3/31994171.jpg	http://www.tcszyy.com/contents/33/235.html
CLIN_ENT	丁必祥	中医师	3110	诊治耳鼻咽喉科的常见病和疑难重症等疾病，开展各类手术治疗。	http://www.tcszyy.com/upload/images/2025/3/319116992.jpg	http://www.tcszyy.com/contents/60/139.html
CLIN_ENT	李明武	主任医师	3109	鼻窦炎鼻息肉、小儿鼾症、咽喉肿瘤、鼓膜穿孔、慢性泪囊炎的内镜及微创治疗。	http://www.tcszyy.com/upload/images/2025/3/319126576.jpg	http://www.tcszyy.com/contents/60/138.html
CLIN_ENT	王旭	主治中医师	3108	耳鼻咽喉常见病多发病的中西医结合诊疗及常规手术。	http://www.tcszyy.com/upload/images/2025/3/319130205.jpg	http://www.tcszyy.com/contents/60/136.html
CLIN_ENT	王素銮	医师	3108	耳鼻咽喉科常见病多发病的诊疗及常规手术。	http://www.tcszyy.com/upload/images/2025/3/319143893.JPG	http://www.tcszyy.com/contents/60/135.html
CLIN_DENT	张浩哲	医师	1号楼三层西	牙体牙髓病、牙周病、颌面外伤、各类牙拔除术、牙体牙列缺失缺损修复等。	http://www.tcszyy.com/upload/images/2025/3/3192059621.jpg	http://www.tcszyy.com/contents/39/2566.html
CLIN_DENT	李平	主治医师	1号楼三层西	牙齿缺失、烤瓷牙修复、各类牙列不齐的矫治，开展颌面部肿瘤、外伤、唇腭裂修复等口腔外科手术。	http://www.tcszyy.com/upload/images/2025/3/319153186.jpg	http://www.tcszyy.com/contents/39/158.html
CLIN_DENT	段君一	主治医师	1号楼三层西	错颌畸形矫治、儿童早期颌面管理、口腔种植、固定及活动义齿的设计修复、牙体牙髓病的诊治和复杂牙拔除等。	http://www.tcszyy.com/upload/images/2025/3/3195510328.jpg	http://www.tcszyy.com/contents/39/157.html
CLIN_DENT	崇殿芳	主治医师	1号楼三层西	口腔外科小手术切除、各类牙齿拔除、牙髓病、根尖周病、牙周病、口腔粘膜病及儿童牙病等。	http://www.tcszyy.com/upload/images/2025/3/3191755729.jpg	http://www.tcszyy.com/contents/39/156.html
CLIN_DENT	陈玉卿	主治医师	1号楼三层西	牙体牙髓病和牙周病诊治、牙体牙列缺失缺损修复、种植牙修复、牙列不齐矫正及颌面外科手术等。	http://www.tcszyy.com/upload/images/2025/3/3191852572.jpg	http://www.tcszyy.com/contents/39/155.html
CLIN_DENT	贡玉萍	主治医师	1号楼三层西	牙体牙髓病的诊治，牙体牙列缺失修复，各类牙找除术	http://www.tcszyy.com/upload/images/2025/3/3191936910.jpg	http://www.tcszyy.com/contents/39/153.html
CLIN_DERM	邓娴	医师	3023	治疗皮肤科常见病、多发病，以及常见皮肤病的激光治疗。	http://www.tcszyy.com/upload/images/2025/3/3195542500.jpg	http://www.tcszyy.com/contents/36/2567.html
CLIN_DERM	徐文琴	副主任中医师	3023	皮肤科疾病诊治，特别是运用中西医结合方法治疗“白癜风”、“扁平疣”、“寒冷性多形红斑”等各种顽固性皮肤病。	http://www.tcszyy.com/upload/images/2025/3/3192153106.jpg	http://www.tcszyy.com/contents/36/217.html
CLIN_DERM	叶宇峰	中医师	3023	皮肤科常见病、多发病的诊治，能运用中西医结合方法治疗“痤疮”、“跖疣”、“带状疱疹”等顽固性皮肤病。	http://www.tcszyy.com/upload/images/2025/3/3192246573.jpg	http://www.tcszyy.com/contents/36/216.html
CLIN_DERM	王春芳	主治中医师	3025	运用中西医结合方法治疗皮肤科常见病、多发病等顽固性皮肤病。	http://www.tcszyy.com/upload/images/2025/3/3192333788.jpg	http://www.tcszyy.com/contents/36/215.html
CLIN_DERM	赵业琴	主治中医师	3023	皮肤科湿疹、荨麻疹、银屑病、病毒性疣、真菌等病的诊治，及常规激光治疗。	http://www.tcszyy.com/upload/images/2025/3/319254841.jpg	http://www.tcszyy.com/contents/36/214.html
CLIN_PROCT	林贤江	主治中医师	3036	内痔、外痔、混合痔、肛瘘、肛裂、肛周脓肿等肛肠外科常见病多发病诊治。	http://www.tcszyy.com/upload/images/2025/3/3193436374.jpg	http://www.tcszyy.com/contents/42/2571.html
CLIN_PROCT	程昊	主治中医师	3036	肛肠外科常见病及罕见病的诊治和普通外科疾病综合治疗等。	http://www.tcszyy.com/upload/images/2025/3/3195231556.jpg	http://www.tcszyy.com/contents/42/2570.html
CLIN_PROCT	高燕	主治医师	3036	大肠肛门疾病的中西医结合诊治。	http://www.tcszyy.com/upload/images/2025/3/3193251448.jpg	http://www.tcszyy.com/contents/42/2569.html
CLIN_PROCT	黎荣幸	主治医师	3036	肛肠科和普外科的常见病多发病诊治。	http://www.tcszyy.com/upload/images/2025/3/319321518.jpg	http://www.tcszyy.com/contents/42/2568.html
CLIN_PROCT	姜志明	主治医师	2010	运用中西医结合方法诊治心脑血管病、消化系统疾病及肛肠科疑难杂病。	http://www.tcszyy.com/upload/images/2025/3/319273900.jpg	http://www.tcszyy.com/contents/42/152.html
CLIN_PROCT	徐恒满	副主任中医师	3036	肛肠外科常见病、炎症性肠病及罕见病的中西医结合诊治和普通外科疾病手术治疗等。	http://www.tcszyy.com/upload/images/2025/3/319281646.jpg	http://www.tcszyy.com/contents/42/151.html
CLIN_PROCT	司旭华	主治医师	3037	内痔、外痔、混合痔、肛瘘、肛裂、肛周脓肿等肛肠外科常见病、多发病诊治。 。	http://www.tcszyy.com/upload/images/2025/3/319305802.jpg	http://www.tcszyy.com/contents/42/150.html
CLIN_PROCT	顾世明	主治医师	3028	普外科及肛肠科常见病多发病的诊治。	http://www.tcszyy.com/upload/images/2025/3/319314313.jpg	http://www.tcszyy.com/contents/42/149.html
CLIN_ANDRO	夏文生	中医师	2030	男女不孕不育症、性功能疾病、性传播疾病、前列腺病等。	http://www.tcszyy.com/upload/images/2025/3/3193530798.jpg	http://www.tcszyy.com/contents/57/159.html
CLIN_SMOKE	黄书谦	副主任中医师	2019	致力于帮助有志戒烟人土成功戒烟，提供专业的指导，并对其进行长期随访、监督和管理，运用中西医结合方法解决戒烟过程中出现的不适并及时调整戒烟策略，提高其戒烟成功率。	http://www.tcszyy.com/upload/images/2025/3/3193655762.jpg	http://www.tcszyy.com/contents/255/1854.html
"""


def _doctor_cards() -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for line in _PUBLIC_DOCTOR_CARDS_TSV.splitlines():
        if not line.strip():
            continue
        department_code, name, title, room, specialty, avatar_url, profile_url = line.split("\t")
        cards.append({
            "department_code": department_code,
            "name": name,
            "title": title,
            "room": room,
            "introduction": specialty,
            "avatar_url": avatar_url,
            "profile_url": profile_url,
        })
    return cards


def doctors_with_departments() -> list[dict[str, object]]:
    """按姓名合并官网重复卡片，同时保留全部科室关系和第一张公开头像。"""
    merged: dict[str, dict[str, object]] = {}
    for card in _doctor_cards():
        name = card["name"]
        item = merged.get(name)
        if item is None:
            item = {**card, "department_codes": [card["department_code"]]}
            merged[name] = item
            continue
        department_codes = item["department_codes"]
        if card["department_code"] not in department_codes:
            department_codes.append(card["department_code"])
        if card["department_code"] == "CLIN_SMOKE":
            item["introduction"] = card["introduction"]
    for name, primary_code in PRIMARY_DEPARTMENT_OVERRIDES.items():
        item = merged.get(name)
        if item is None:
            continue
        department_codes = item["department_codes"]
        if primary_code in department_codes:
            department_codes.remove(primary_code)
            department_codes.insert(0, primary_code)
            item["department_code"] = primary_code
    return list(merged.values())
