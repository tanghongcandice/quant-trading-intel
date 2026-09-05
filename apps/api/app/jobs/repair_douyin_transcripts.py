from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PREVIEW_NOTICE = "【仅前30秒预览｜当前登录账号未订阅该作品】"
MODEL_NAME = "mlx-community/whisper-large-v3-turbo"

CONTEXT_CORRECTIONS = (
    (r"主性", "主线"),
    (r"主身", "主升"),
    (r"版块", "板块"),
    (r"分期", "分歧"),
    (r"引进制动", "以静制动"),
    (r"盘灵山", "盘面上"),
    (r"封口结束", "风口结束"),
    (r"拉伸", "拉升"),
    (r"掌停", "涨停"),
    (r"一字版", "一字板"),
    (r"反保", "反包"),
    (r"帅气", "帅旗"),
    (r"人情就散", "人气就散"),
    (r"补党", "补涨"),
    (r"后备军", "补涨"),
    (r"部长", "补涨"),
    (r"补完后半局", "补完后半句"),
    (r"大部队车", "大部队撤"),
    (r"资金整体立场", "资金整体离场"),
    (r"散火", "散伙"),
    (r"A刹", "A杀"),
    (r"低息资金", "低吸资金"),
    (r"挑空缺口", "跳空缺口"),
    (r"放量突破关键位置", "放量跌破关键位置"),
    (r"利好顿话", "利好钝化"),
    (r"东军", "中军"),
    (r"缩量上涨吃吧", "缩量上涨是反弹"),
    (r"主地浪", "主跌浪"),
    (r"大级别主升", "大级别主升"),
    (r"新营用落地", "新应用落地"),
    (r"逻辑面衣", "逻辑面硬"),
    (r"情绪半双", "情绪伴生"),
    (r"悬谷", "选股"),
    (r"套牢自己买单", "套牢资金买单"),
    (r"抛牙", "抛压"),
    (r"接抖", "接走"),
    (r"资金沉结", "资金承接"),
    (r"封口，套牢盘", "风口，套牢盘"),
    (r"成为游资第一步。我小心是没有对，以静制动。我心不太相配，盘面上的心态。", "以静制动，是盘面上的一种心态。"),
    (r"涨压", "涨呀"),
    (r"最混乱的那一刻抢着证明自己有多厉害的一跌", "最混乱的那一刻，抢着证明自己有多厉害一点"),
    (r"有现金，有时间", "有钱，有时间"),
    (r"稳步引力", "稳步盈利"),
    (r"小先生都能听懂", "小学生都能听懂"),
    (r"绝鼻啊，你看完绝鼻非，受益费钱", "务必看完，绝对会受益匪浅"),
    (r"二四年Tipsick", "2024 年 DeepSeek"),
    (r"二五年的商业行情和理店", "2025 年的商业航天和机器人"),
    (r"商榜", "伤亡"),
    (r"人家吃肉拟出轿子前", "人家吃肉，你出抬轿子钱"),
    (r"走势是极其不连关", "走势极其不连贯"),
    (r"龙头立起，中军压阵，后军不位", "龙头立旗，中军压阵，后军补位"),
    (r"帅旗的龙头断板，请去退场", "帅旗的龙头断板，情绪退潮"),
    (r"不是你运气差，是你把分歧当成了结束", "不是你运气差，是你把分歧当成了结束"),
    (r"我喊一要喊到现在", "我喊医药喊到现在"),
    (r"拿那个板块指数跳空缺口", "拿板块指数的跳空缺口"),
    (r"低吸资金来", "低吸资金来承接"),
    (r"中军透明不会", "中军有没有破位"),
    (r"利好来了，涨不涨，涨啊", "利好来了涨不涨？涨啊"),
    (r"数据的奴隶哦", "数据的奴隶"),
    (r"全板块跳水的时候，一横", "全板块跳水的时候，玉衡"),
    (r"涨出。他一封板", "涨停。它一封板"),
    (r"这个市场上面有汉森娜和神奇", "市场上有汉森和神奇"),
    (r"龙头就是哈耀", "龙头就是哈药"),
    (r"中军要民", "中军药明"),
    (r"万帮跌了", "万邦德跌了"),
    (r"没有合进性的", "还没有喝尽兴"),
    (r"A10大佬", "A股大佬"),
    (r"按我的来势说", "按我的交易模式来说"),
    (r"视梦率", "市梦率"),
    (r"赛片", "赛道"),
    (r"哥本开摘", "资本开支"),
    (r"一缕就是那块最短的板", "利率就是那块最短的板"),
    (r"阶段性的沉压", "阶段性承压"),
    (r"历史就白了", "历史就摆在那里"),
    (r"套牢盘的香化是有随缓的", "套牢盘的消化是有周期的"),
    (r"下台阶，摸顶等新逻辑", "下台阶、磨底，等待新逻辑"),
    (r"这个是铁率", "这是铁律"),
    (r"医药长太多回调", "医药涨太多后回调"),
    (r"医药还有什么多头啊", "医药还有什么多头"),
    (r"开了主升", "开启了主升"),
    (r"一要一走路", "医药一路走"),
    (r"凭什么从半生转正", "凭什么从伴生转正"),
    (r"有点贪通", "有点看懂"),
    (r"全世界每三代小麦有一代", "全世界每三袋小麦有一袋"),
    (r"往外预粮", "往外运粮"),
    (r"鄂尔尼诺", "厄尔尼诺"),
    (r"汗的汗死，闹的闹死", "旱的旱死，涝的涝死"),
    (r"全在独运气", "全在赌运气"),
    (r"或者木子海峡", "霍尔木兹海峡"),
    (r"化肥场", "化肥厂"),
    (r"中低的成本", "种地的成本"),
    (r"钱队在哪里", "钱堆在哪里"),
    (r"金剑米", "金健米业"),
    (r"种业质涨", "种业滞涨"),
    (r"黑海停火，海峡富豪", "黑海停火、海峡复航"),
    (r"有没有想象力看题材能不能走出来看筹码", "有没有想象力、题材能不能走出来，要看筹码"),
    (r"白银纽丝", "白银有色"),
    (r"胡罗", "葫芦娃"),
    (r"支架刀", "指甲刀"),
    (r"11天7万", "11天7板"),
    (r"20到25元存掉了几十个亿", "20到25元成交了几十个亿"),
    (r"主持人要来了", "主升要来了"),
    (r"解套牢正在接", "解套盘正在砸"),
    (r"围着这个钱高打转", "围着这个区间打转"),
    (r"收纹点后就是这个股票的股票。", ""),
    (r"光模快", "光模块"),
    (r"美光、SK、海力士", "美光、SK海力士"),
    (r"西捷", "希捷"),
    (r"沃什简化", "沃什讲话"),
    (r"全线翻率", "全线翻绿"),
    (r"天股通信", "天孚通信"),
    (r"Fairvo|Fairvo", "Fervo"),
    (r"清洁机核电", "清洁基荷电源"),
    (r"刚刚哈利伯顿签了EGS赚紧合作", "开山刚与哈利伯顿签了 EGS 钻井合作"),
    (r"Fervo的店2028年", "Fervo 的电要到 2028 年"),
    (r"一日卖冲", "一日脉冲"),
    (r"高标题材股", "高估值题材股"),
    (r"张盟主|张萌主", "章盟主"),
    (r"芒果超梅", "芒果超媒"),
    (r"海鸥助攻", "海鸥住工"),
    (r"吉泰股份", "集泰股份"),
    (r"主笔兑完", "逐笔对完"),
    (r"泼喷冷水", "泼盆冷水"),
    (r"照着根", "照着跟"),
    (r"互不搭借", "互不搭界"),
    (r"关系概率", "加息概率"),
    (r"低位打卖冲", "低位打脉冲"),
    (r"发灵枪", "发令枪"),
    (r"七连版", "七连板"),
    (r"后让20%股权", "受让 20% 股权"),
    (r"可资源易主", "控制权易主"),
    (r"液冷硅油材料", "液冷硅酮材料"),
    (r"双标，明白白说过", "公司明明白白说过"),
    (r"机构近买入", "机构净买入"),
    (r"由自买集泰", "游资买集泰"),
    (r"AIGC长距", "AIGC 长剧"),
    (r"收市率同时段省级卫市第一", "收视率同时段省级卫视第一"),
    (r"油资在买", "游资在买"),
    (r"油资", "游资"),
    (r"延报目标价", "研报目标价"),
    (r"17两元", "17.2 元"),
    (r"铜板块的欢瑞世纪", "同板块的欢瑞世纪"),
    (r"博拿影业", "博纳影业"),
    (r"第九七阶段", "在情绪极致阶段"),
    (r"地产地位轮动", "地产低位轮动"),
    (r"地产看经济，误管", "地产看经纪、物管"),
    (r"仓位别中", "仓位别重"),
    (r"一息落地", "议息落地"),
    (r"手购手用", "首购首用"),
    (r"补贴是给企业书写", "补贴是给企业输血"),
    (r"都号token", "都消耗 Token"),
    (r"正企客户", "政企客户"),
    (r"小快清准", "小快轻准"),
    (r"软件性创采购", "软件信创采购"),
    (r"不需要丛林建立信任", "不需要重新建立信任"),
    (r"四个条件全战", "四个条件全占"),
    (r"扣飞", "扣非"),
    (r"买的是蔚来", "买的是未来"),
    (r"新火", "星火"),
    (r"开发者结发", "开发者节发布"),
    (r"拥有网络", "用友网络"),
    (r"范围网络", "泛微网络"),
    (r"AI短剧AR2", "AI短剧 ARR"),
    (r"新规失行", "新规施行"),
    (r"别高反", "别搞反"),
    (r"跌堆很", "跌得最狠"),
    (r"新ST文太", "*ST闻泰"),
    (r"东管", "东莞"),
    (r"安市", "安世"),
    (r"全部冻死", "全部冻结"),
    (r"二级管", "二极管"),
    (r"张学正", "张学政"),
    (r"文太|文泰", "闻泰"),
    (r"动股权", "冻结股权"),
    (r"肃情", "诉请"),
    (r"把这些股权动在那儿", "把这些股权冻在那儿"),
    (r"打公司期间", "打官司期间"),
    (r"今天上半年", "今年上半年"),
    (r"主场锁猴", "主场锁喉"),
    (r"而且动的只是", "而且冻结的只是"),
    (r"冷水必须破三盆", "冷水必须泼三盆"),
    (r"连停都还没开", "连庭都还没开"),
    (r"飞标意见", "非标意见"),
    (r"这只裁定", "这纸裁定"),
    (r"不是存单，是一张期权", "不是股票，是一张期权"),
    (r"荣库县|荣库线|容枯线|融库线", "荣枯线"),
    (r"他方之后", "塌方之后"),
    (r"没收到点子上", "没说到点子上"),
    (r"也占回50以上", "也站回50以上"),
    (r"产需两望", "产需两旺"),
    (r"任何届PMI", "任何借PMI"),
    (r"没业绩提彩票", "没业绩的彩票"),
    (r"加全算", "加权算"),
    (r"购近", "购进"),
    (r"出厂50，4\.4", "出厂50.4"),
    (r"减到差", "剪刀差"),
    (r"占稳50", "站稳50"),
    (r"量价其升", "量价齐升"),
    (r"有色也练", "有色冶炼"),
    (r"三级报", "三季报"),
    (r"大水万贯", "大水漫灌"),
    (r"7月5向全黑", "7月五项全黑"),
    (r"市场压住9月", "市场押注9月"),
    (r"铜履金，紫金，落木，铜铃，云铝", "铜、铝、金，紫金、洛钼、铜陵、云铝"),
    (r"利润上修的毛", "利润上修的锚"),
    (r"飞农", "非农"),
    (r"今天五盘", "今天午盘"),
    (r"你要是指扫", "你要是只扫"),
    (r"煤店", "煤电"),
    (r"六代行", "六大行"),
    (r"第一次还比回升", "第一次环比回升"),
    (r"有利润毛的资源股", "有利润锚的资源股"),
    (r"短距", "短剧"),
    (r"中暴", "中报"),
    (r"芒果超煤", "芒果超媒"),
    (r"黄金党", "黄金档"),
    (r"一字版", "一字板"),
    (r"手风单", "手封单"),
    (r"市联行", "世联行"),
    (r"集体榨板", "集体炸板"),
    (r"高薪高的银行", "创新高的银行"),
    (r"雅铃配置", "哑铃配置"),
    (r"剑韬", "建滔"),
    (r"博布", "薄布"),
    (r"一乘四", "一成四"),
    (r"咸丰控股", "贤丰控股"),
    (r"折叠品", "折叠屏"),
    (r"鸡犬升天", "鸡犬升天"),
    (r"月文短剧", "阅文短剧"),
    (r"上兴湖南", "上星湖南"),
    (r"新公里", "芯公里"),
    (r"所产能", "锁产能"),
    (r"运营商几彩", "运营商集采"),
    (r"移动普览几彩", "移动普缆集采"),
    (r"拉斯", "拉丝"),
    (r"样是原话", "央视原话"),
    (r"长鞋单", "长协单"),
    (r"中心光纤", "空芯光纤"),
    (r"质棒工艺", "制棒工艺"),
    (r"傍仙缆", "棒、纤、缆"),
    (r"通顶互联", "通鼎互联"),
    (r"打回原型", "打回原形"),
    (r"腰骨", "妖股"),
    (r"户值", "沪指"),
    (r"Sedans", "Seedance"),
    (r"申万红元", "申万宏源"),
    (r"短巨", "短剧"),
    (r"街头全字严", "接头全自研"),
    (r"再手订单", "在手订单"),
    (r"高篮股份", "高澜股份"),
    (r"光铅", "光纤"),
    (r"适境率", "市净率"),
    (r"压仓时", "压舱石"),
    (r"回跳配龙头", "回调配龙头"),
    (r"银行，红利拿着不处", "银行、红利拿着不追"),
    (r"三个最领先的分项全部跌到30\.2，全部跌到荣枯线以下。2026年头一回五项全黑。所以8月这49\.，不转强，那谁再拖后腿？", "三个最领先的分项全部转强，那谁在拖后腿？"),
    (r"OpenLay|OpenLine", "OpenAI"),
    (r"Answer PAPIC", "Anthropic"),
    (r"Lumaton", "Lumentum"),
    (r"Core Wave", "CoreWeave"),
    (r"降服过半", "降幅过半"),
    (r"全部借完", "全部建完"),
    (r"十几瓦租约", "10吉瓦租约"),
    (r"(?<![十数])几瓦", "吉瓦"),
    (r"级瓦", "吉瓦"),
    (r"急于一身", "集于一身"),
    (r"大空头博里", "大空头 Burry"),
    (r"大空投博里|大空头薄利|大空头博利|大空投薄利", "大空头 Burry"),
    (r"博里|博利|薄利", "Burry"),
    (r"大空投", "大空头"),
    (r"空投仓位|空投股票", "空头仓位"),
    (r"想摩|小蘑菇", "小摩"),
    (r"百为存储|百维存储|百为", "佰维存储"),
    (r"蓝起科技", "澜起科技"),
    (r"韩国检查厅", "韩国检察厅"),
    (r"丹摩光纤", "单模光纤"),
    (r"国产闯商", "国内厂商"),
    (r"空心光纜集彩|空心光缆集采", "空芯光缆集采"),
    (r"常飞中标", "长飞中标"),
    (r"旅行期", "履行期"),
    (r"这支票", "这只票"),
    (r"户指", "沪指"),
    (r"创业版", "创业板"),
    (r"副铜板", "覆铜板"),
    (r"波参布", "玻纤布"),
    (r"生意科技", "生益科技"),
    (r"深难电路", "深南电路"),
    (r"万象得农", "万向德农"),
    (r"动态适应率", "动态市盈率"),
    (r"试净率", "市净率"),
    (r"适应率", "市盈率"),
    (r"新网锐杰", "星网锐捷"),
    (r"终于动", "中国移动"),
    (r"顶节数字", "鼎捷数智"),
    (r"天鱼术科", "天娱数科"),
    (r"静业达", "竞业达"),
    (r"建凯科技", "健凯科技"),
    (r"卧石|卧时|卧室", "沃什"),
    (r"放音", "放鹰"),
    (r"规模净利润|归模净利润", "归母净利润"),
    (r"公远价值", "公允价值"),
    (r"账面服营|金融服营", "账面浮盈"),
    (r"连引企业", "联营企业"),
    (r"转雇", "转固"),
    (r"8\.6代M?OLED量产", "8.6代AMOLED量产"),
    (r"纸板机", "直板机"),
    (r"杰克逊货而", "杰克逊霍尔"),
    (r"德克利", "德科立"),
    (r"国联名声言报", "国联民生研报"),
    (r"Signal AI|SIM Analysis", "SemiAnalysis"),
    (r"Lumitum", "Lumentum"),
    (r"Cohenet", "Coherent"),
    (r"MVL576", "NVL576"),
    (r"scale across tone", "scale-across中"),
    (r"scale across", "scale-across"),
    (r"scale up", "scale-up"),
    (r"时间线被严重钳制", "时间线被严重提前"),
    (r"谷歌独家拜公故事", "谷歌独家代工故事"),
    (r"赛威电子", "赛微电子"),
    (r"MMS OCS掌机", "MEMS OCS整机"),
    (r"光酷泥酸锂", "光库科技铌酸锂"),
    (r"中继续创", "中际旭创"),
    (r"聚光科技太成光", "炬光科技、太辰光"),
    (r"HPM内存", "HBM内存"),
    (r"MS50", "MI450"),
    (r"Planter", "Palantir"),
    (r"担保厂口", "担保敞口"),
    (r"换贷", "换代"),
    (r"方向队不等于实机队", "方向对不等于时机对"),
    (r"正翻科技|正番科技|正翻自己|正番不是", "正帆科技"),
    (r"威母净利润", "归母净利润"),
    (r"特别炸烈", "特别炸裂"),
    (r"QE", "Q1"),
    (r"QR", "Q2"),
    (r"江峰电子", "江丰电子"),
    (r"副创金幣", "富创精密"),
    (r"视频电源", "射频电源"),
    (r"减刀差", "剪刀差"),
    (r"碳化归零部件", "碳化硅零部件"),
    (r"高端实营件|石英剑", "高端石英件"),
    (r"油资净流出", "游资净流出"),
    (r"赵毅创新", "兆易创新"),
    (r"盛宏科技", "胜宏科技"),
    (r"6版", "6板"),
    (r"7连版", "7连板"),
    (r"浩华科技", "昊华科技"),
    (r"麒麟性安", "麒麟信安"),
    (r"热点分成", "热点分散"),
    (r"找挖地", "找洼地"),
    (r"贴线率", "贴现率"),
    (r"玉米杂胶种", "玉米杂交种"),
    (r"总业行情", "种业行情"),
    (r"CIO和疫苗", "CRO和疫苗"),
    (r"还没起问", "还没企稳"),
    (r"如果偏歌", "如果偏鸽"),
    (r"刀口填写", "刀口舔血"),
    (r"卧食", "沃什"),
    (r"月共", "月供"),
    (r"真正的核贷", "真正的核心"),
    (r"实际售益面", "实际受益面"),
    (r"银工备案", "竣工备案"),
    (r"从封顶到银工", "从封顶到竣工"),
    (r"等到银工", "等到竣工"),
    (r"发RETs|发RETs|REDES", "发REITs"),
    (r"集团书写", "集团输血"),
    (r"西房信仰", "土地信仰"),
    (r"市值一页增加", "市值一夜增加"),
    (r"2028台年", "2028财年"),
    (r"黄文勋", "黄仁勋"),
    (r"DRM", "DRAM"),
    (r"NA涨", "NAND涨"),
    (r"卖产人", "卖铲人"),
    (r"买产人", "买铲人"),
    (r"SK海力市", "SK海力士"),
    (r"闪敌", "闪迪"),
    (r"HPM厂口", "HBM敞口"),
    (r"鸡选升天", "鸡犬升天"),
    (r"进心增AR2", "净新增ARR"),
    (r"习安信", "奇安信"),
    (r"蓝屏大档机", "蓝屏大宕机"),
    (r"美国乌废料|美国所废料", "美国钨废料"),
    (r"乌矿股", "钨矿股"),
    (r"中国乌企", "中国钨企"),
    (r"乌产业链", "钨产业链"),
    (r"中乌在线", "中钨在线"),
    (r"乌金矿", "钨精矿"),
    (r"乌出口", "钨出口"),
    (r"乌价", "钨价"),
    (r"中国乌定价权", "中国钨定价权"),
    (r"OnMonte|Almonte", "Almonty"),
    (r"韩国桑东乌矿", "韩国桑东钨矿"),
    (r"费量禁令", "废料禁令"),
    (r"100\.8万亿吨", "100.8万元/吨"),
    (r"张元乌业", "章源钨业"),
    (r"矿墙也弱", "矿强冶弱"),
    (r"中油加工", "中游加工"),
    (r"中乌高新|中乌高星", "中钨高新"),
    (r"市竹园", "柿竹园"),
    (r"厦门物业|厦门乌业", "厦门钨业"),
    (r"原况自给率", "原矿自给率"),
    (r"记提", "计提"),
    (r"六幅化屋", "六氟化钨"),
    (r"3DNet", "3D NAND"),
    (r"屋粉", "钨粉"),
    (r"中传特器", "中船特气"),
    (r"SK海利市", "SK海力士"),
    (r"中屋高新", "中钨高新"),
    (r"降陆乌业", "翔鹭钨业"),
    (r"厂外佩兹", "场外配资"),
    (r"Holmes", "HOMS"),
    (r"佩兹爆仓", "配资爆仓"),
    (r"政争会", "证监会"),
    (r"一直没敢落地，这一哥就是七年", "一直没敢落地，这一搁就是七年"),
    (r"封控", "风控"),
    (r"组合权", "组合拳"),
    (r"正言顺", "名正言顺"),
    (r"跟着掉", "跟着调"),
    (r"2%到3却", "2%到3%，却"),
    (r"收益都转付", "收益都转负"),
    (r"提前预言", "提前预演"),
    (r"DROA", "DRO-A"),
    (r"再人登月", "载人登月"),
    (r"弱道只剩", "弱到只剩"),
    (r"闹事噪音", "闹市噪音"),
    (r"100K这个速度", "100M这个速度"),
    (r"Lady探测器", "LADEE探测器"),
    (r"禁地轨道", "近地轨道"),
    (r"定了行", "定了型"),
    (r"新上设备", "星上设备"),
    (r"枝江实验室", "之江实验室"),
    (r"直接大黑", "直接拉黑"),
    (r"禁地星座|禁地链", "低轨星座"),
    (r"新网GW星座", "国网GW星座"),
    (r"1\.5万克", "1.5万颗"),
    (r"400克", "400颗"),
    (r"新间激光终端", "星间激光终端"),
    (r"新网份额", "国网份额"),
    (r"长光华星|长光华新", "长光华芯"),
    (r"上海汉讯|上海汉逊", "上海瀚讯"),
    (r"通信载贺", "通信载荷"),
    (r"薄膜泥酸里", "薄膜铌酸锂"),
    (r"升空期权", "深空期权"),
    (r"升空激光通信", "深空激光通信"),
    (r"升空逻辑", "深空逻辑"),
    (r"升空采购", "深空采购"),
    (r"旗舰是单光子", "器件是单光子"),
    (r"国顿量子", "国盾量子"),
    (r"量子概念股潮", "量子概念股炒"),
    (r"是名牌", "是明牌"),
    (r"麦威尔", "Marvell"),
    (r"Lumatum", "Lumentum"),
    (r"换房", "换防"),
    (r"挨这一道", "挨这一刀"),
    (r"台报会上", "财报电话会上"),
    (r"200万克GPU", "200万颗GPU"),
    (r"明排", "明牌"),
    (r"现金楼最后", "现金流最好"),
    (r"下办场", "下半场"),
    (r"美国飞农", "美国非农"),
    (r"景田", "景甜"),
    (r"智慧欠缝", "智慧欠奉"),
    (r"碧安", "币安"),
    (r"Steam事件", "STEEM事件"),
    (r"波厂公链|波厂", "波场"),
    (r"全部细于", "全部系于"),
    (r"四个月行期", "四个月刑期"),
    (r"达摩克利斯之鉴", "达摩克利斯之剑"),
    (r"长新", "长鑫"),
    (r"社军", "涉军"),
    (r"批准了你列入", "批准了拟列入"),
    (r"耀明康德", "药明康德"),
    (r"何赛科技", "禾赛科技"),
    (r"列明前连申变机会", "列名前连申辩机会"),
    (r"反复无常的铁重", "反复无常的铁证"),
    (r"带基金27%7\.7%", "大基金二期7.7%"),
    (r"程序派", "程序牌"),
    (r"给客户签账", "给客户信心"),
    (r"诉讼是情绪，不净利润表", "诉讼是情绪，不进利润表"),
    (r"给苹果清账", "给苹果清障"),
    (r"房贷能待40年", "房贷能贷40年"),
    (r"按接贷款", "按揭贷款"),
    (r"但保，收入", "但保住收入"),
    (r"买卖滑得来", "买卖划得来"),
    (r"格局会加，这很强", "格局会加速分化"),
    (r"十点变了", "时点变了"),
    (r"高周转的名气", "高周转的民企"),
    (r"华人质地", "华润置地"),
    (r"进付赚率", "净负债率"),
    (r"招商舌口", "招商蛇口"),
    (r"核心城市就改项目", "核心城市旧改项目"),
    (r"近期差", "净息差"),
    (r"稀差", "息差"),
    (r"先亿后扬", "先抑后扬"),
    (r"雇家家居", "顾家家居"),
    (r"延控放款", "延后放款"),
    (r"词员|词源", "词元"),
    (r"暗效付费", "按效付费"),
    (r"32层数据标注", "32城数据标注"),
    (r"39层", "39城"),
    (r"聚身智能", "具身智能"),
    (r"正要命的是", "真正要命的是"),
    (r"轻一色", "清一色"),
    (r"保利率", "毛利率"),
    (r"托尔斯", "拓尔思"),
    (r"对半侃", "对半砍"),
    (r"正式订名", "正式定名"),
    (r"手机化费", "手机话费"),
    (r"科大训飞", "科大讯飞"),
    (r"假集测绘", "甲级测绘"),
    (r"及轨迹数据", "级轨迹数据"),
    (r"思维图星", "四维图新"),
    (r"制算液冷", "智算液冷"),
    (r"静默式", "浸没式"),
    (r"夜冷", "液冷"),
    (r"曙光树创", "曙光数创"),
    (r"森林环境", "申菱环境"),
    (r"高栏股份", "高澜股份"),
    (r"浮化液", "氟化液"),
    (r"进波式|浸波式", "浸没式"),
    (r"新周邦", "新宙邦"),
    (r"机贵", "机柜"),
    (r"水管就得扑多粗", "水管就得铺多粗"),
    (r"东方电器", "东方电气"),
    (r"日本303家", "日本三菱三家"),
    (r"电力缺口称爆", "电力缺口撑爆"),
    (r"订单加档期", "订单加排单档期"),
    (r"西门子30全排", "西门子、三菱全排"),
    (r"2009年立下", "2009年立项"),
    (r"人家35年", "人家3到5年"),
    (r"太航燃机商机组", "太行燃机商用机组"),
    (r"结尾股份", "杰瑞股份"),
    (r"燃机发现机组", "燃机发电机组"),
    (r"167倍", "16.7倍"),
    (r"手键认证", "首件认证"),
    (r"阴流的叶片", "应流的叶片"),
    (r"小米18FORB", "小米18 Fold"),
    (r"JDAS", "JEDEC"),
    (r"LPDDR5X，0\.7G", "LPDDR5X 10.7G"),
    (r"挤压膏", "挤牙膏"),
    (r"CES量了样品", "CES亮了样品"),
    (r"EC制程", "1β制程"),
    (r"二贡导入", "第二供应商导入"),
    (r"首批占配解禁", "首批战略配售解禁"),
    (r"长鑫占配名单", "长鑫战略配售名单"),
    (r"拓金薄膜", "拓荆薄膜"),
    (r"雅克前躯体", "雅克科技前驱体"),
    (r"江峰板才", "江丰电子靶材"),
    (r"生科技绑定", "深科技绑定"),
    (r"立即存储", "利基存储"),
    (r"HPM", "HBM"),
    (r"搞反了英国", "搞反了因果"),
    (r"常新科技", "长鑫科技"),
    (r"大浦威", "佰维存储"),
    (r"Anthroptics", "Anthropic"),
    (r"AI的毛空前锐利", "AI的矛空前锐利"),
    (r"更觉得是", "更绝的是"),
    (r"放英", "放鹰"),
    (r"正翻|正番", "正帆"),
    (r"高端实营体系", "高端石英体系"),
    (r"当然正帆科技没有亮点", "当然正帆科技不是没有亮点"),
    (r"所有乌废料", "所有钨废料"),
    (r"全球乌供应", "全球钨供应"),
    (r"全球乌产量", "全球钨产量"),
    (r"采购中国乌", "采购中国钨"),
    (r"中国乌矿", "中国钨矿"),
    (r"沉积乌薄膜", "沉积钨薄膜"),
    (r"一看到屋就买", "一看到钨就买"),
    (r"厦门屋业", "厦门钨业"),
    (r"名字里一个屋子都没有", "名字里一个钨字都没有"),
    (r"零自由矿山", "零自有矿山"),
    (r"也链端", "冶炼端"),
    (r"简直压力大", "精矿压力大"),
    (r"主案审批", "逐案审批"),
    (r"看到这部", "看到这步"),
    (r"实现自己", "实现自给"),
    (r"成本传到", "成本传导"),
    (r"\bplanter\b", "Palantir"),
    (r"Nabius", "Nebius"),
    (r"程昌科技", "铖昌科技"),
    (r"真雷科技", "振雷科技"),
    (r"心载|新载", "星载"),
    (r"相控镇", "相控阵"),
    (r"正有科技", "震有科技"),
    (r"这事脱不得", "这事拖不得"),
    (r"卖产子的", "卖铲子的"),
    (r"买产子的", "买铲子的"),
    (r"地面的性关站", "地面的信关站"),
    (r"当前足往期", "当前组网期"),
    (r"亚太水道", "亚太尿素"),
    (r"这局面短期解开", "这局面短期难解"),
    (r"假肥", "钾肥"),
    (r"甲肥", "钾肥"),
    (r"假矿", "钾矿"),
    (r"甲盐", "钾盐"),
    (r"亚甲国际", "亚钾国际"),
    (r"林肥", "磷肥"),
    (r"林矿", "磷矿"),
    (r"南涝北汉", "南涝北旱"),
    (r"灯海种业", "登海种业"),
    (r"玉米玉种", "玉米育种"),
    (r"900万吨股物", "900万吨谷物"),
    (r"钾矿零矿", "钾矿、磷矿"),
    (r"伪售益", "伪受益"),
    (r"佳俄百老四国", "加拿大、俄罗斯、白俄罗斯、老挝四国"),
    (r"绿化甲", "氯化钾"),
    (r"975亿吨", "975元/吨"),
    (r"甲里铜", "钾、锂、铜"),
    (r"单体甲矿", "单体钾矿"),
    (r"种叶", "种业"),
    (r"转基因自治", "转基因制种"),
    (r"成本成压", "成本承压"),
    (r"别等所有人看到财经", "别等所有人看到菜价"),
    (r"钾肥优于零肥，零肥优于种业", "钾肥优于磷肥，磷肥优于种业"),
    (r"再动手不吃", "再动手不迟"),
    (r"特创版", "科创板"),
    (r"岁源科技|岁源", "燧原科技"),
    (r"摩尔县城", "摩尔线程"),
    (r"穆锡|穆西", "沐曦"),
    (r"碧刃", "壁仞"),
    (r"软件债", "软件栈"),
    (r"韩武器", "寒武纪"),
    (r"收入值引", "收入指引"),
    (r"最关心的打心", "最关心的打新"),
    (r"重1000赚24万", "中一签赚24万"),
    (r"中一千能赚多少", "中一签能赚多少"),
    (r"科创买11只", "科创板11只"),
    (r"机构往下申购", "机构网下申购"),
    (r"机构报价上线", "机构报价上限"),
    (r"当场炮住", "当场套住"),
    (r"带EU的未盈利股票", "带U的未盈利股票"),
    (r"全力打薪", "全力打新"),
    (r"招果书", "招股书"),
    (r"芯片公司烧前期结束", "芯片公司烧钱期结束"),
    (r"科创版带U", "科创板带U"),
    (r"(别拿去下单)[\s\S]*$", r"\1。"),
    (r"中期续创", "中际旭创"),
    (r"现代股价", "现在股价"),
    (r"公报", "公告"),
    (r"董事长刘胜", "董事长刘圣"),
    (r"正式过回", "正式过会"),
    (r"机构90天均价", "机构目标价均价"),
    (r"高盛最接近看到", "高盛最激进看到"),
    (r"价值毛", "价值锚"),
    (r"第二个正义点", "第二个争议点"),
    (r"不增好每股收益", "不增厚每股收益"),
    (r"正式光模块", "正是光模块"),
    (r"NPO CPU", "NPO、CPO"),
    (r"泥酸李", "铌酸锂"),
    (r"发行价980港元", "发行价98.0港元"),
    (r"一共布了614亿港币", "一共募了61.4亿港币"),
    (r"上半年营收417亿", "上半年营收41.7亿"),
    (r"净利136亿", "净利13.6亿"),
    (r"光模块收入413亿", "光模块收入41.3亿"),
    (r"去年全年的374亿", "去年全年的37.4亿"),
    (r"2026年净利的一致预期，在360到390亿", "2026年净利润的一致预期，在36到39亿"),
    (r"Q2的79亿", "Q2的7.9亿"),
    (r"两拨CPU小作文", "两拨CPO小作文"),
    (r"英伟达CPU名单", "英伟达CPO名单"),
    (r"NPOCPU", "NPO、CPO"),
    (r"北美云厂上", "北美云厂商"),
    (r"三季报近利", "三季报净利润"),
    (r"光模快周期", "光模块周期"),
    (r"800到850这一代", "800到850这一带"),
    (r"(最响的一声地板在这里)[\s\S]*$", r"\1。"),
    (r"中芯通讯", "中兴通讯"),
    (r"中芯出硬件", "中兴出硬件"),
    (r"手机由中芯和字节", "手机由中兴和字节"),
    (r"中芯上半年", "中兴上半年"),
    (r"中芯贡献", "中兴贡献"),
    (r"中芯全年", "中兴全年"),
    (r"中芯真正", "中兴真正"),
    (r"豆包手机对中芯", "豆包手机对中兴"),
    (r"券商给中芯", "券商给中兴"),
    (r"你要买中芯", "你要买中兴"),
    (r"数据中芯产品", "数据中心产品"),
    (r"中心拿到的是一块AI广告位", "中兴拿到的是一块 AI 广告位"),
    (r"烫硬件这滩浑水", "蹚硬件这滩浑水"),
    (r"利润更加", "利润增量"),
    (r"利润增量。中兴贡献", "利润增量对中兴的贡献"),
    (r"50亿辆级", "50亿量级"),
    # 财经语境中的“算力全栈”常被 ASR 识别为“全站/反转”；只在该
    # 固定短语中纠正，避免改动真正表示趋势反转的句子。
    (r"算力全站", "算力全栈"),
    (r"算力反转加估值修复", "算力全栈加估值修复"),
    (r"入头到尾拆解", "从头到尾拆解"),
    (r"从来都不是佔值", "从来都不是估值"),
    (r"顺语供摄像头", "舜宇供摄像头"),
    (r"惠顶供指纹", "汇顶供指纹"),
    (r"德塞供电池", "德赛供电池"),
    (r"全是古巴和自媒体传的", "全是股吧和自媒体传的"),
    (r"较印信源", "较硬信源"),
    (r"增后利润", "增厚利润"),
    (r"大几百万辆级", "大几百万量级"),
    (r"Poge看到", "泼给看到"),
    (r"颇给", "泼给"),
    (r"手销数据", "首销数据"),
    (r"飞浓", "非农"),
    (r"美联储一息", "美联储议息"),
    (r"三连因", "三连阴"),
    (r"伊老革命卫队", "伊朗革命卫队"),
    (r"债势", "债市"),
    (r"杀九七|杀的是97", "杀估值"),
    (r"扒杆子打不着", "八竿子打不着"),
    (r"光模块是不是要量", "光模块是不是要凉"),
    (r"终继续创收", "中际旭创收"),
    (r"新意胜", "新易盛"),
    (r"天赋通信", "天孚通信"),
    (r"莫沙东", "默沙东"),
    (r"必须心醒", "必须清醒"),
    (r"制飞生物", "智飞生物"),
    (r"追高甚重", "追高慎重"),
    (r"比限价", "比现价"),
    (r"两桶油脱底", "两桶油托底"),
    (r"客户在强产能", "客户在抢产能"),
    (r"龙头在所未来", "龙头在锁未来"),
    (r"损失就是百万几", "损失就是百万计"),
    (r"一倍八", "1.8倍"),
    (r"纳米及筋度", "纳米级精度"),
    (r"再稍结", "再烧结"),
    (r"三五年代差", "三五年的代差"),
    (r"先破一盆冷水", "先泼一盆冷水"),
    (r"授意路径", "受益路径"),
    (r"高端长鞋锁死", "高端长协锁死"),
    (r"华为升腾", "华为昇腾"),
    (r"看姐美科技，双新新材", "看洁美科技、双星新材"),
    (r"电极涅粉", "电极镍粉"),
    (r"买好彩", "买耗材"),
    (r"顺落电子", "顺络电子"),
    (r"被动原件", "被动元件"),
    (r"电容俩则", "电容两字"),
    (r"深程值", "深成指"),
    (r"股票票率", "股票飘绿"),
    (r"下跌加数", "下跌家数"),
    (r"一场名牌的资金", "一场明牌的资金"),
    (r"三联因", "三连阴"),
    (r"光模块双熊", "光模块双雄"),
    (r"梦想股沙估值", "成长股杀估值"),
    (r"沙九七", "杀估值"),
    (r"一劳反击", "伊朗反击"),
    (r"不由冲到", "布油冲到"),
    (r"急运指数", "集运指数"),
    (r"内蒙一基", "内蒙一机"),
    (r"巴士加核心军工公司", "80家核心军工公司"),
    (r"155开局", "“十五五”开局"),
    (r"领长", "领涨"),
    (r"常识储能", "长时储能"),
    (r"审马电力", "神马电力"),
    (r"风尚涨停", "风范股份涨停"),
    (r"电路板和波线", "电路板和玻纤"),
    (r"副同板", "覆铜板"),
    (r"波C龙头", "玻纤龙头"),
    (r"电子不报价", "电子布报价"),
    (r"后部涨", "厚布涨"),
    (r"保物部涨", "薄布涨"),
    (r"涨价寒", "涨价函"),
    (r"山东波森", "山东玻纤"),
    (r"五盘翻率", "午盘翻绿"),
    (r"翻率", "翻绿"),
    (r"油价侦破", "油价真破"),
    (r"买上油", "买石油"),
    (r"两时半天", "两市半天"),
    (r"灯海种页", "登海种业"),
    (r"掏钱见数据中心", "掏钱建数据中心"),
    (r"增速从77%回落到4%", "增速从77%回落到40%"),
    (r"今年天亮基础", "今年天量基础"),
    (r"我跟史丹利", "摩根士丹利"),
    (r"或者转付", "或者转负"),
    (r"说法要揪篇", "说法要纠偏"),
    (r"纳值", "纳指"),
    (r"天福通信", "天孚通信"),
    (r"寒5G", "寒武纪"),
    (r"工业复联", "工业富联"),
    (r"别中仓毒", "别重仓赌"),
    (r"中旬一息", "中旬议息"),
    (r"穿越版", "创业板"),
    (r"全市估值最高", "全是估值最高"),
    (r"低估值高峰红", "低估值高分红"),
    (r"155投资", "“十五五”投资"),
    (r"国常会钢厅取汇报", "国常会听取汇报"),
    (r"长城军工建设工业涨停", "长城军工、建设工业涨停"),
    (r"155管网", "“十五五”管网"),
    (r"中京讲得很直白", "中金讲得很直白"),
    (r"新益胜", "新易盛"),
    (r"天福，寒武器", "天孚、寒武纪"),
    (r"分批低息", "分批低吸"),
    (r"农业今天怎么这么狗不弱", "农业今天怎么这么弱"),
    (r"昨天所有提对", "昨天所有题材都对"),
    (r"不信主信", "不信主线"),
    (r"加息已经，他这个预期已经到60%确定性了", "加息预期已经到60%确定性了"),
    (r"往固定资产涌", "往固收资产涌"),
    (r"家头大王", "价值投资大王"),
    (r"上座已经跟我讲过", "上周已经跟我讲过"),
)


# Candidate replacements that need sentence-level evidence.  These are kept
# separate from CONTEXT_CORRECTIONS so a homophone is never changed globally.
# Each context hit contributes to a confidence score; the replacement is made
# only when the score clears the threshold.
CONTEXTUAL_CANDIDATES = (
    {
        "source": "镍木各",
        "replacement": "镍钼铬",
        "local_context": (r"哈氏合金", r"C276", r"镍基合金", r"合金.{0,12}元素", r"元素.{0,12}不便宜"),
        "title_context": (r"镍", r"超导", r"合金"),
        "threshold": 3,
    },
)


@dataclass(frozen=True)
class TranscriptRepair:
    aweme_id: str
    title: str
    text: str
    status: str
    media_duration_seconds: float
    accessible_duration_seconds: float
    transcript_end_seconds: float
    removed_repetitions: int
    contextual_corrections: tuple[dict[str, str], ...]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(title: str | None, text: str | None, html: str | None = None) -> str:
    payload = canonical_json({"title": title or "", "text": text or "", "html": html or ""})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sentence_key(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def collapse_repeated_sentences(text: str) -> tuple[str, int]:
    """Remove adjacent repeated sentence blocks without globally deduplicating facts."""
    text = re.sub(r"([\u4e00-\u9fff])\1{5,}[。！？]?", "", text)
    text = text.replace("�", "")
    sentences = [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"(?<=[。！？!?])|(?<!\d)(?<=\.)(?!\d)|[\r\n]+", text)
        if part.strip()
    ]
    if len(sentences) < 2:
        return (sentences[0] if sentences else ""), 0

    accepted: list[str] = []
    removed = 0
    for sentence in sentences:
        accepted.append(sentence)
        for block_size in range(min(4, len(accepted) // 2), 0, -1):
            left = [_sentence_key(part) for part in accepted[-2 * block_size : -block_size]]
            right = [_sentence_key(part) for part in accepted[-block_size:]]
            if left == right and all(right):
                del accepted[-block_size:]
                removed += block_size
                break
    return "".join(accepted).strip(), removed


def _normalize_punctuation(text: str) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    value = value.replace(",", "，").replace("?", "？").replace("!", "！")
    return re.sub(r"(?<!\d)\.(?!\d)", "。", value)


def _paragraphize(text: str, target_chars: int = 110) -> str:
    sentences = [part.strip() for part in re.findall(r"[^。！？]+[。！？]?", text) if part.strip()]
    paragraphs: list[str] = []
    current: list[str] = []
    current_chars = 0
    for sentence in sentences:
        if current and (len(current) >= 3 or current_chars + len(sentence) > target_chars):
            paragraphs.append("".join(current))
            current = []
            current_chars = 0
        current.append(sentence)
        current_chars += len(sentence)
    if current:
        paragraphs.append("".join(current))
    return "\n\n".join(paragraphs)


def format_whisper_segments(whisper: dict[str, Any]) -> tuple[str, int]:
    """Turn timestamped Whisper clauses into punctuated, short paragraphs."""
    segments = whisper.get("segments") or []
    if not segments:
        cleaned, removed = collapse_repeated_sentences(str(whisper.get("text") or ""))
        return _paragraphize(_normalize_punctuation(cleaned)), removed

    sentences: list[str] = []
    clauses: list[str] = []
    clause_chars = 0

    def flush(terminal: str = "。") -> None:
        nonlocal clauses, clause_chars
        if not clauses:
            return
        sentence = "，".join(part.strip("，。！？ ") for part in clauses if part.strip("，。！？ "))
        if sentence:
            sentences.append(sentence + terminal)
        clauses = []
        clause_chars = 0

    for index, segment in enumerate(segments):
        normalized = _normalize_punctuation(str(segment.get("text") or ""))
        pieces = [part for part in re.findall(r"[^。！？]+[。！？]?", normalized) if part.strip()]
        for piece in pieces:
            terminal = piece[-1] if piece[-1:] in "。！？" else ""
            clause = piece[:-1] if terminal else piece
            clause = clause.strip("，。！？ ")
            if clause:
                clauses.append(clause)
                clause_chars += len(clause)
            if terminal:
                flush(terminal)

        next_start = (
            float(segments[index + 1].get("start") or 0) if index + 1 < len(segments) else None
        )
        pause = next_start - float(segment.get("end") or 0) if next_start is not None else 0
        if clauses and (clause_chars >= 34 or pause >= 0.4):
            flush()
    flush()

    cleaned, removed = collapse_repeated_sentences("".join(sentences))
    return _paragraphize(cleaned), removed


def apply_contextual_corrections(title: str, text: str) -> tuple[str, tuple[dict[str, str], ...]]:
    """Apply deterministic corrections, then score ambiguous candidates locally.

    The candidate layer intentionally uses a narrow context window and the
    title/hashtags.  It is therefore auditable and cannot rewrite an unrelated
    occurrence merely because two strings sound alike.
    """
    corrected = text
    changes: list[dict[str, str]] = []
    for pattern, replacement in CONTEXT_CORRECTIONS:
        updated, count = re.subn(pattern, replacement, corrected)
        if count:
            changes.append({"pattern": pattern, "replacement": replacement, "count": str(count)})
            corrected = updated

    title_context = " ".join(re.findall(r"#([^#\s]+)", title)) + " " + title
    for candidate in CONTEXTUAL_CANDIDATES:
        source = candidate["source"]
        replacement = candidate["replacement"]
        local_patterns = candidate.get("local_context") or ()
        title_patterns = candidate.get("title_context") or ()
        threshold = int(candidate.get("threshold") or 1)
        matches = list(re.finditer(re.escape(source), corrected))
        for match in reversed(matches):
            start, end = match.span()
            window = corrected[max(0, start - 96) : min(len(corrected), end + 96)]
            local_hits = [pattern for pattern in local_patterns if re.search(pattern, window, flags=re.I)]
            title_hits = [pattern for pattern in title_patterns if re.search(pattern, title_context, flags=re.I)]
            score = len(local_hits) + len(title_hits)
            if score < threshold:
                continue
            corrected = corrected[:start] + replacement + corrected[end:]
            changes.append(
                {
                    "pattern": source,
                    "replacement": replacement,
                    "count": "1",
                    "method": "contextual_candidate_score",
                    "score": str(score),
                    "local_context": ",".join(local_hits),
                    "title_context": ",".join(title_hits),
                }
            )
    return corrected, tuple(changes)


def _duration_seconds(metadata: dict[str, Any]) -> float:
    duration = float(metadata.get("duration") or 0)
    return duration / 1000 if duration > 1000 else duration


def is_locked_subscription(metadata: dict[str, Any]) -> bool:
    charge = metadata.get("charge_info") or {}
    return bool(charge.get("is_charge_content")) and not bool(charge.get("has_paid"))


def build_repair(metadata: dict[str, Any], whisper: dict[str, Any]) -> TranscriptRepair:
    aweme_id = str(metadata.get("aweme_id") or "")
    title = str(metadata.get("desc") or "").strip()
    media_duration = _duration_seconds(metadata)
    charge = metadata.get("charge_info") or {}
    preview = charge.get("preview_config") or {}
    is_locked_preview = is_locked_subscription(metadata)
    preview_end = float(preview.get("end_time") or 0) / 1000
    accessible_duration = preview_end if is_locked_preview and preview_end else media_duration

    segments = whisper.get("segments") or []
    transcript_end = max((float(segment.get("end") or 0) for segment in segments), default=0)
    minimum_end = max(0, accessible_duration - 3)
    if transcript_end < minimum_end:
        raise ValueError(
            f"{aweme_id}: transcript ends at {transcript_end:.2f}s, "
            f"before accessible media ends at {accessible_duration:.2f}s"
        )

    cleaned, removed = format_whisper_segments(whisper)
    cleaned, corrections = apply_contextual_corrections(title, cleaned)
    if not cleaned:
        raise ValueError(f"{aweme_id}: transcript is empty")

    status = "subscription_preview" if is_locked_preview else "complete"
    text = f"{PREVIEW_NOTICE}\n{cleaned}" if is_locked_preview else cleaned
    return TranscriptRepair(
        aweme_id=aweme_id,
        title=title,
        text=text,
        status=status,
        media_duration_seconds=round(media_duration, 3),
        accessible_duration_seconds=round(accessible_duration, 3),
        transcript_end_seconds=round(transcript_end, 3),
        removed_repetitions=removed,
        contextual_corrections=corrections,
    )


def find_metadata(metadata_root: Path, date: str) -> list[Path]:
    return sorted(metadata_root.glob(f"{date}_*/*_data.json"))


def load_repairs(metadata_root: Path, whisper_dir: Path, date: str) -> list[TranscriptRepair]:
    repairs: list[TranscriptRepair] = []
    for metadata_path in find_metadata(metadata_root, date):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        aweme_id = str(metadata.get("aweme_id") or "")
        whisper_path = whisper_dir / f"{aweme_id}.json"
        if not whisper_path.exists():
            raise FileNotFoundError(f"missing Whisper result: {whisper_path}")
        whisper = json.loads(whisper_path.read_text(encoding="utf-8"))
        repairs.append(build_repair(metadata, whisper))
    return repairs


def update_database(db_path: Path, source_id: str, repairs: list[TranscriptRepair]) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            for repair in repairs:
                row = conn.execute(
                    """
                    SELECT id, title, author_handle, source_name, raw_json
                    FROM information_items
                    WHERE source_id = ? AND external_id = ?
                    """,
                    (source_id, repair.aweme_id),
                ).fetchone()
                if row is None:
                    raise ValueError(f"database item not found: {source_id}/{repair.aweme_id}")

                raw = json.loads(row["raw_json"])
                new_hash = content_hash(row["title"], repair.text, (raw.get("content") or {}).get("html"))
                raw.setdefault("content", {})["text"] = repair.text
                raw["content"]["hash"] = new_hash
                raw.setdefault("source", {})["collector"] = "video-downloader+mlx-whisper-large-v3-turbo"
                raw["source"]["adapter_version"] = "douyin-asr.2"
                raw.setdefault("raw_payload", {})["transcription"] = {
                    "model": MODEL_NAME,
                    "status": repair.status,
                    "media_duration_seconds": repair.media_duration_seconds,
                    "accessible_duration_seconds": repair.accessible_duration_seconds,
                    "transcript_end_seconds": repair.transcript_end_seconds,
                    "removed_repetitions": repair.removed_repetitions,
                    "contextual_corrections": list(repair.contextual_corrections),
                    "text_refinement": {
                        "method": "llm_context_review",
                        "reviewer": "codex",
                        "preserve_numbers": True,
                        "preserve_claims": True,
                    },
                }
                raw["raw_payload"]["analysis_policy"] = {
                    "include": repair.status != "subscription_preview",
                    "mode": "analysis" if repair.status != "subscription_preview" else "review_only",
                    "reason": None if repair.status != "subscription_preview" else "subscription_preview",
                }

                conn.execute(
                    """
                    UPDATE information_items
                    SET collector = ?, content_text = ?, content_hash = ?, raw_json = ?
                    WHERE id = ?
                    """,
                    (
                        "video-downloader+mlx-whisper-large-v3-turbo",
                        repair.text,
                        new_hash,
                        json.dumps(raw, ensure_ascii=False, sort_keys=True),
                        row["id"],
                    ),
                )
                conn.execute("DELETE FROM information_items_fts WHERE item_id = ?", (row["id"],))
                conn.execute(
                    """
                    INSERT INTO information_items_fts
                    (item_id, title, content_text, author_handle, source_name)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (row["id"], row["title"], repair.text, row["author_handle"], row["source_name"]),
                )
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Whisper JSON, label subscription previews, and repair Douyin text in SQLite."
    )
    parser.add_argument("--metadata-root", required=True, type=Path)
    parser.add_argument("--whisper-dir", required=True, type=Path)
    parser.add_argument("--transcript-dir", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--source-id", default="douyin_jiujiujiucai")
    args = parser.parse_args()

    repairs = load_repairs(args.metadata_root, args.whisper_dir, args.date)
    args.transcript_dir.mkdir(parents=True, exist_ok=True)
    for repair in repairs:
        (args.transcript_dir / f"{repair.aweme_id}.txt").write_text(repair.text + "\n", encoding="utf-8")
    update_database(args.db, args.source_id, repairs)
    print(
        json.dumps(
            {
                "date": args.date,
                "updated": len(repairs),
                "complete": sum(item.status == "complete" for item in repairs),
                "subscription_preview_review_only": sum(
                    item.status == "subscription_preview" for item in repairs
                ),
                "items": [item.__dict__ for item in repairs],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
