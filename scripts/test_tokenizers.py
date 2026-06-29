"""测试不同分词器对实体名的效果"""
import jieba

names = [
    '浙江省羽毛球队', '浙江羽毛球队', '浙江队', '浙江省游泳队',
    '中国国家羽毛球队', '银川高铁站', '银川站',
    '亚洲羽毛球锦标赛', '斯诺克亚锦赛', '全国游泳冠军赛',
    '中国台北羽毛球代表队', '日本国家羽毛球队'
]

print("=== jieba 默认 ===")
for n in names:
    print(f"  {n:20s} -> {' | '.join(jieba.cut(n))}")

# 添加体育领域词
jieba.add_word("羽毛球队")
jieba.add_word("羽毛")
jieba.add_word("游泳队")
jieba.add_word("亚锦赛")
jieba.add_word("斯诺克")
jieba.add_word("高铁站")

print("\n=== jieba + 领域词典 ===")
for n in names:
    print(f"  {n:20s} -> {' | '.join(jieba.cut(n))}")
