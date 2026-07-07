"""POI 种子数据：5个热门城市的景点/餐厅/酒店/交通枢纽。

每个 POI 包含：name, address, category, ticket, stay_time, cost_estimate, place_type
启动时写入 SQLite pois 表，以后查询直接走数据库，0次地图API。
"""
from __future__ import annotations

import time
import uuid

POI_SEED: dict[str, list[dict]] = {
    "杭州": [
        # 景点
        {"name": "灵隐寺", "address": "杭州市西湖区灵隐路法云弄1号", "category": "scenic", "ticket": 75, "stay_time": 120, "cost_estimate": 75, "place_type": "scenic"},
        {"name": "西湖", "address": "杭州市西湖区龙井路1号", "category": "scenic", "ticket": 0, "stay_time": 180, "cost_estimate": 0, "place_type": "scenic"},
        {"name": "雷峰塔", "address": "杭州市西湖区南山路15号", "category": "scenic", "ticket": 40, "stay_time": 60, "cost_estimate": 40, "place_type": "scenic"},
        {"name": "西溪湿地", "address": "杭州市西湖区天目山路518号", "category": "scenic", "ticket": 80, "stay_time": 180, "cost_estimate": 80, "place_type": "scenic"},
        {"name": "宋城", "address": "杭州市之江路148号", "category": "scenic", "ticket": 300, "stay_time": 300, "cost_estimate": 300, "place_type": "scenic"},
        {"name": "河坊街", "address": "杭州市上城区河坊街", "category": "scenic", "ticket": 0, "stay_time": 90, "cost_estimate": 0, "place_type": "scenic"},
        {"name": "千岛湖", "address": "杭州市淳安县千岛湖镇", "category": "scenic", "ticket": 130, "stay_time": 360, "cost_estimate": 130, "place_type": "scenic"},
        # 餐厅
        {"name": "楼外楼", "address": "杭州市西湖区孤山路30号", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 200, "place_type": "restaurant"},
        {"name": "知味观", "address": "杭州市上城区仁和路83号", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 120, "place_type": "restaurant"},
        {"name": "外婆家", "address": "杭州市西湖区马塍路6-1号", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 80, "place_type": "restaurant"},
        {"name": "新白鹿餐厅", "address": "杭州市下城区凤起路261号", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 80, "place_type": "restaurant"},
        {"name": "奎元馆", "address": "杭州市上城区解放路154号", "category": "restaurant", "ticket": 0, "stay_time": 60, "cost_estimate": 50, "place_type": "restaurant"},
        # 酒店
        {"name": "西湖国宾馆", "address": "杭州市西湖区杨公堤18号", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 800, "place_type": "hotel"},
        {"name": "杭州黄龙饭店", "address": "杭州市西湖区曙光路120号", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 500, "place_type": "hotel"},
        {"name": "如家酒店西湖店", "address": "杭州市西湖区杭大路28号", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 250, "place_type": "hotel"},
        # 交通
        {"name": "杭州东站", "address": "杭州市江干区天城路1号", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
        {"name": "杭州萧山机场", "address": "杭州市萧山区机场高速", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
    ],
    "北京": [
        # 景点
        {"name": "故宫", "address": "北京市东城区景山前街4号", "category": "scenic", "ticket": 60, "stay_time": 180, "cost_estimate": 60, "place_type": "scenic"},
        {"name": "天坛公园", "address": "北京市东城区天坛内东里7号", "category": "scenic", "ticket": 34, "stay_time": 120, "cost_estimate": 34, "place_type": "scenic"},
        {"name": "颐和园", "address": "北京市海淀区新建宫门路19号", "category": "scenic", "ticket": 60, "stay_time": 180, "cost_estimate": 60, "place_type": "scenic"},
        {"name": "长城", "address": "北京市延庆区八达岭特区", "category": "scenic", "ticket": 40, "stay_time": 240, "cost_estimate": 40, "place_type": "scenic"},
        {"name": "天安门广场", "address": "北京市东城区东长安街", "category": "scenic", "ticket": 0, "stay_time": 60, "cost_estimate": 0, "place_type": "scenic"},
        {"name": "鸟巢", "address": "北京市朝阳区国家体育场南路1号", "category": "scenic", "ticket": 50, "stay_time": 90, "cost_estimate": 50, "place_type": "scenic"},
        {"name": "南锣鼓巷", "address": "北京市东城区南锣鼓巷", "category": "scenic", "ticket": 0, "stay_time": 90, "cost_estimate": 0, "place_type": "scenic"},
        # 餐厅
        {"name": "全聚德烤鸭店", "address": "北京市东城区前门大街30号", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 250, "place_type": "restaurant"},
        {"name": "东来顺涮羊肉", "address": "北京市东城区王府井大街198号", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 180, "place_type": "restaurant"},
        {"name": "便宜坊烤鸭", "address": "北京市东城区崇文门外大街16号", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 200, "place_type": "restaurant"},
        {"name": "护国寺小吃", "address": "北京市西城区护国寺大街93号", "category": "restaurant", "ticket": 0, "stay_time": 60, "cost_estimate": 50, "place_type": "restaurant"},
        # 酒店
        {"name": "北京饭店", "address": "北京市东城区东长安街33号", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 600, "place_type": "hotel"},
        {"name": "如家酒店前门店", "address": "北京市东城区前门东路", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 280, "place_type": "hotel"},
        {"name": "锦江之星王府井店", "address": "北京市东城区东华门大街", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 300, "place_type": "hotel"},
        # 交通
        {"name": "北京南站", "address": "北京市丰台区永外大街车站路12号", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
        {"name": "首都机场", "address": "北京市顺义区首都机场路", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
    ],
    "西安": [
        # 景点
        {"name": "兵马俑", "address": "西安市临潼区秦陵北路", "category": "scenic", "ticket": 120, "stay_time": 180, "cost_estimate": 120, "place_type": "scenic"},
        {"name": "大雁塔", "address": "西安市雁塔区雁塔南路", "category": "scenic", "ticket": 30, "stay_time": 90, "cost_estimate": 30, "place_type": "scenic"},
        {"name": "华清宫", "address": "西安市临潼区华清路38号", "category": "scenic", "ticket": 120, "stay_time": 120, "cost_estimate": 120, "place_type": "scenic"},
        {"name": "城墙", "address": "西安市碑林区南大街", "category": "scenic", "ticket": 54, "stay_time": 120, "cost_estimate": 54, "place_type": "scenic"},
        {"name": "回民街", "address": "西安市莲湖区北院门", "category": "scenic", "ticket": 0, "stay_time": 90, "cost_estimate": 0, "place_type": "scenic"},
        {"name": "陕西历史博物馆", "address": "西安市雁塔区小寨东路91号", "category": "scenic", "ticket": 0, "stay_time": 150, "cost_estimate": 0, "place_type": "scenic"},
        # 餐厅
        {"name": "老孙家羊肉泡馍", "address": "西安市碑林区东大街364号", "category": "restaurant", "ticket": 0, "stay_time": 60, "cost_estimate": 60, "place_type": "restaurant"},
        {"name": "同盛祥", "address": "西安市莲湖区西大街5号", "category": "restaurant", "ticket": 0, "stay_time": 60, "cost_estimate": 55, "place_type": "restaurant"},
        {"name": "长安大牌档", "address": "西安市雁塔区小寨西路", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 100, "place_type": "restaurant"},
        {"name": "魏家凉皮", "address": "西安市碑林区南大街", "category": "restaurant", "ticket": 0, "stay_time": 45, "cost_estimate": 25, "place_type": "restaurant"},
        # 酒店
        {"name": "西安钟楼饭店", "address": "西安市碑林区社会路8号", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 450, "place_type": "hotel"},
        {"name": "如家酒店钟楼店", "address": "西安市碑林区东大街", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 220, "place_type": "hotel"},
        # 交通
        {"name": "西安北站", "address": "西安市未央区元朔路", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
        {"name": "咸阳机场", "address": "西安市咸阳国际机场", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
    ],
    "成都": [
        # 景点
        {"name": "宽窄巷子", "address": "成都市青羊区宽窄巷子", "category": "scenic", "ticket": 0, "stay_time": 120, "cost_estimate": 0, "place_type": "scenic"},
        {"name": "武侯祠", "address": "成都市武侯区武侯祠大街231号", "category": "scenic", "ticket": 50, "stay_time": 90, "cost_estimate": 50, "place_type": "scenic"},
        {"name": "杜甫草堂", "address": "成都市青羊区青华路37号", "category": "scenic", "ticket": 50, "stay_time": 90, "cost_estimate": 50, "place_type": "scenic"},
        {"name": "锦里", "address": "成都市武侯区武侯祠大街", "category": "scenic", "ticket": 0, "stay_time": 90, "cost_estimate": 0, "place_type": "scenic"},
        {"name": "大熊猫繁育基地", "address": "成都市成华区外北熊猫大道1375号", "category": "scenic", "ticket": 55, "stay_time": 180, "cost_estimate": 55, "place_type": "scenic"},
        {"name": "都江堰", "address": "成都市都江堰市公园路", "category": "scenic", "ticket": 80, "stay_time": 180, "cost_estimate": 80, "place_type": "scenic"},
        # 餐厅
        {"name": "陈麻婆豆腐", "address": "成都市青羊区青华路10号", "category": "restaurant", "ticket": 0, "stay_time": 60, "cost_estimate": 60, "place_type": "restaurant"},
        {"name": "小龙坎火锅", "address": "成都市锦江区下东大街", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 120, "place_type": "restaurant"},
        {"name": "蜀大侠火锅", "address": "成都市武侯区一环路西一段", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 110, "place_type": "restaurant"},
        {"name": "钟水饺", "address": "成都市青羊区羊市街", "category": "restaurant", "ticket": 0, "stay_time": 45, "cost_estimate": 30, "place_type": "restaurant"},
        # 酒店
        {"name": "成都香格里拉酒店", "address": "成都市锦江区滨江东路9号", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 700, "place_type": "hotel"},
        {"name": "如家酒店春熙路店", "address": "成都市锦江区春熙路", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 230, "place_type": "hotel"},
        # 交通
        {"name": "成都东站", "address": "成都市成华区邛崃山路", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
        {"name": "双流机场", "address": "成都市双流区机场路", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
    ],
    "上海": [
        # 景点
        {"name": "外滩", "address": "上海市黄浦区中山东一路", "category": "scenic", "ticket": 0, "stay_time": 90, "cost_estimate": 0, "place_type": "scenic"},
        {"name": "东方明珠", "address": "上海市浦东新区世纪大道1号", "category": "scenic", "ticket": 120, "stay_time": 120, "cost_estimate": 120, "place_type": "scenic"},
        {"name": "迪士尼乐园", "address": "上海市浦东新区川沙镇", "category": "scenic", "ticket": 435, "stay_time": 480, "cost_estimate": 435, "place_type": "scenic"},
        {"name": "豫园", "address": "上海市黄浦区安仁街218号", "category": "scenic", "ticket": 40, "stay_time": 90, "cost_estimate": 40, "place_type": "scenic"},
        {"name": "南京路步行街", "address": "上海市黄浦区南京东路", "category": "scenic", "ticket": 0, "stay_time": 120, "cost_estimate": 0, "place_type": "scenic"},
        {"name": "上海博物馆", "address": "上海市黄浦区人民大道201号", "category": "scenic", "ticket": 0, "stay_time": 120, "cost_estimate": 0, "place_type": "scenic"},
        # 餐厅
        {"name": "南翔馒头店", "address": "上海市黄浦区豫园路85号", "category": "restaurant", "ticket": 0, "stay_time": 60, "cost_estimate": 60, "place_type": "restaurant"},
        {"name": "上海老饭店", "address": "上海市黄浦区福佑路242号", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 150, "place_type": "restaurant"},
        {"name": "小杨生煎", "address": "上海市黄浦区吴江路", "category": "restaurant", "ticket": 0, "stay_time": 45, "cost_estimate": 30, "place_type": "restaurant"},
        {"name": "鼎泰丰", "address": "上海市浦东新区世纪大道", "category": "restaurant", "ticket": 0, "stay_time": 90, "cost_estimate": 180, "place_type": "restaurant"},
        # 酒店
        {"name": "上海外滩茂悦大酒店", "address": "上海市黄浦路199号", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 800, "place_type": "hotel"},
        {"name": "如家酒店南京路店", "address": "上海市黄浦区南京东路", "category": "hotel", "ticket": 0, "stay_time": 600, "cost_estimate": 300, "place_type": "hotel"},
        # 交通
        {"name": "上海虹桥站", "address": "上海市闵行区申虹路", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
        {"name": "浦东机场", "address": "上海市浦东新区启航路", "category": "transport", "ticket": 0, "stay_time": 30, "cost_estimate": 0, "place_type": "transport"},
    ],
}


async def seed_pois(db) -> None:
    """将种子数据写入 pois 表（如果不存在）。"""
    now = time.time()
    for city, pois in POI_SEED.items():
        for poi in pois:
            poi_id = f"seed-{city}-{poi['name']}"
            # 检查是否已存在
            cursor = await db.execute("SELECT id FROM pois WHERE id = ?", (poi_id,))
            if await cursor.fetchone():
                continue
            await db.execute(
                """INSERT OR REPLACE INTO pois (id, city, name, address, category, ticket, stay_time, cost_estimate, place_type, lat, lng, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)""",
                (poi_id, city, poi["name"], poi["address"], poi["category"],
                 poi["ticket"], poi["stay_time"], poi["cost_estimate"], poi["place_type"], now),
            )
    await db.commit()
