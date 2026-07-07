"""中国城市数据服务：支持模糊搜索。

数据来源：内置中国主要城市列表（直辖市、省会、地级市）。
后续可替换为外部 API。
"""
from __future__ import annotations

# 中国主要城市列表（按拼音排序，覆盖直辖市、省会及主要地级市）
CHINA_CITIES: list[dict[str, str]] = [
    {"name": "北京", "province": "北京", "pinyin": "beijing"},
    {"name": "上海", "province": "上海", "pinyin": "shanghai"},
    {"name": "广州", "province": "广东", "pinyin": "guangzhou"},
    {"name": "深圳", "province": "广东", "pinyin": "shenzhen"},
    {"name": "杭州", "province": "浙江", "pinyin": "hangzhou"},
    {"name": "南京", "province": "江苏", "pinyin": "nanjing"},
    {"name": "苏州", "province": "江苏", "pinyin": "suzhou"},
    {"name": "成都", "province": "四川", "pinyin": "chengdu"},
    {"name": "重庆", "province": "重庆", "pinyin": "chongqing"},
    {"name": "武汉", "province": "湖北", "pinyin": "wuhan"},
    {"name": "西安", "province": "陕西", "pinyin": "xian"},
    {"name": "长沙", "province": "湖南", "pinyin": "changsha"},
    {"name": "天津", "province": "天津", "pinyin": "tianjin"},
    {"name": "青岛", "province": "山东", "pinyin": "qingdao"},
    {"name": "厦门", "province": "福建", "pinyin": "xiamen"},
    {"name": "昆明", "province": "云南", "pinyin": "kunming"},
    {"name": "大连", "province": "辽宁", "pinyin": "dalian"},
    {"name": "三亚", "province": "海南", "pinyin": "sanya"},
    {"name": "海口", "province": "海南", "pinyin": "haikou"},
    {"name": "丽江", "province": "云南", "pinyin": "lijiang"},
    {"name": "大理", "province": "云南", "pinyin": "dali"},
    {"name": "桂林", "province": "广西", "pinyin": "guilin"},
    {"name": "阳朔", "province": "广西", "pinyin": "yangshuo"},
    {"name": "拉萨", "province": "西藏", "pinyin": "lasa"},
    {"name": "乌鲁木齐", "province": "新疆", "pinyin": "wulumuqi"},
    {"name": "兰州", "province": "甘肃", "pinyin": "lanzhou"},
    {"name": "银川", "province": "宁夏", "pinyin": "yinchuan"},
    {"name": "西宁", "province": "青海", "pinyin": "xining"},
    {"name": "呼和浩特", "province": "内蒙古", "pinyin": "huhehaote"},
    {"name": "哈尔滨", "province": "黑龙江", "pinyin": "haerbin"},
    {"name": "长春", "province": "吉林", "pinyin": "changchun"},
    {"name": "沈阳", "province": "辽宁", "pinyin": "shenyang"},
    {"name": "郑州", "province": "河南", "pinyin": "zhengzhou"},
    {"name": "洛阳", "province": "河南", "pinyin": "luoyang"},
    {"name": "济南", "province": "山东", "pinyin": "jinan"},
    {"name": "合肥", "province": "安徽", "pinyin": "hefei"},
    {"name": "黄山", "province": "安徽", "pinyin": "huangshan"},
    {"name": "南昌", "province": "江西", "pinyin": "nanchang"},
    {"name": "福州", "province": "福建", "pinyin": "fuzhou"},
    {"name": "泉州", "province": "福建", "pinyin": "quanzhou"},
    {"name": "太原", "province": "山西", "pinyin": "taiyuan"},
    {"name": "石家庄", "province": "河北", "pinyin": "shijiazhuang"},
    {"name": "承德", "province": "河北", "pinyin": "chengde"},
    {"name": "贵阳", "province": "贵州", "pinyin": "guiyang"},
    {"name": "南宁", "province": "广西", "pinyin": "nanning"},
    {"name": "珠海", "province": "广东", "pinyin": "zhuhai"},
    {"name": "汕头", "province": "广东", "pinyin": "shantou"},
    {"name": "佛山", "province": "广东", "pinyin": "foshan"},
    {"name": "东莞", "province": "广东", "pinyin": "dongguan"},
    {"name": "惠州", "province": "广东", "pinyin": "huizhou"},
    {"name": "中山", "province": "广东", "pinyin": "zhongshan"},
    {"name": "湛江", "province": "广东", "pinyin": "zhanjiang"},
    {"name": "扬州", "province": "江苏", "pinyin": "yangzhou"},
    {"name": "无锡", "province": "江苏", "pinyin": "wuxi"},
    {"name": "常州", "province": "江苏", "pinyin": "changzhou"},
    {"name": "徐州", "province": "江苏", "pinyin": "xuzhou"},
    {"name": "宁波", "province": "浙江", "pinyin": "ningbo"},
    {"name": "温州", "province": "浙江", "pinyin": "wenzhou"},
    {"name": "绍兴", "province": "浙江", "pinyin": "shaoxing"},
    {"name": "嘉兴", "province": "浙江", "pinyin": "jiaxing"},
    {"name": "金华", "province": "浙江", "pinyin": "jinhua"},
    {"name": "舟山", "province": "浙江", "pinyin": "zhoushan"},
    {"name": "九江", "province": "江西", "pinyin": "jiujiang"},
    {"name": "景德镇", "province": "江西", "pinyin": "jingdezhen"},
    {"name": "宜昌", "province": "湖北", "pinyin": "yichang"},
    {"name": "张家界", "province": "湖南", "pinyin": "zhangjiajie"},
    {"name": "凤凰", "province": "湖南", "pinyin": "fenghuang"},
    {"name": "都江堰", "province": "四川", "pinyin": "dujiangyan"},
    {"name": "九寨沟", "province": "四川", "pinyin": "jiuzhaigou"},
    {"name": "峨眉山", "province": "四川", "pinyin": "emeishan"},
    {"name": "乐山", "province": "四川", "pinyin": "leshan"},
    {"name": "稻城", "province": "四川", "pinyin": "daocheng"},
    {"name": "西双版纳", "province": "云南", "pinyin": "xishuangbanna"},
    {"name": "香格里拉", "province": "云南", "pinyin": "xianggelila"},
    {"name": "腾冲", "province": "云南", "pinyin": "tengchong"},
    {"name": "呼伦贝尔", "province": "内蒙古", "pinyin": "hulunbeier"},
    {"name": "敦煌", "province": "甘肃", "pinyin": "dunhuang"},
    {"name": "嘉峪关", "province": "甘肃", "pinyin": "jiayuguan"},
    {"name": "平遥", "province": "山西", "pinyin": "pingyao"},
    {"name": "五台山", "province": "山西", "pinyin": "wutaishan"},
    {"name": "秦皇岛", "province": "河北", "pinyin": "qinhuangdao"},
    {"name": "北戴河", "province": "河北", "pinyin": "beidaihe"},
    {"name": "威海", "province": "山东", "pinyin": "weihai"},
    {"name": "烟台", "province": "山东", "pinyin": "yantai"},
    {"name": "泰安", "province": "山东", "pinyin": "taian"},
    {"name": "曲阜", "province": "山东", "pinyin": "qufu"},
    {"name": "蓬莱", "province": "山东", "pinyin": "penglai"},
    {"name": "武夷山", "province": "福建", "pinyin": "wuyishan"},
    {"name": "鼓浪屿", "province": "福建", "pinyin": "gulangyu"},
    {"name": "青海湖", "province": "青海", "pinyin": "qinghaihu"},
    {"name": "茶卡盐湖", "province": "青海", "pinyin": "chakayanhu"},
    {"name": "纳木错", "province": "西藏", "pinyin": "namucuo"},
    {"name": "林芝", "province": "西藏", "pinyin": "linzhi"},
    {"name": "日喀则", "province": "西藏", "pinyin": "rikaze"},
    {"name": "阿勒泰", "province": "新疆", "pinyin": "aletai"},
    {"name": "喀纳斯", "province": "新疆", "pinyin": "kanasi"},
    {"name": "伊犁", "province": "新疆", "pinyin": "yili"},
    {"name": "吐鲁番", "province": "新疆", "pinyin": "tulufan"},
]


def search_cities(keyword: str, limit: int = 15) -> list[dict[str, str]]:
    """模糊搜索城市，支持中文和拼音匹配。"""
    kw = keyword.strip().lower()
    if not kw:
        # 无关键词时返回热门城市
        popular = ["北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "厦门", "三亚", "丽江"]
        return [c for c in CHINA_CITIES if c["name"] in popular][:limit]

    results = []
    for city in CHINA_CITIES:
        # 中文包含匹配或拼音前缀匹配
        if kw in city["name"] or city["pinyin"].startswith(kw) or kw in city["pinyin"]:
            results.append(city)
            if len(results) >= limit:
                break
    return results
