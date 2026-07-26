# 导入必要的库
from mido import MidiFile  # 用于处理MIDI文件
from collections import Counter  # 用于计数和统计

# 加载MIDI文件
midi = MidiFile('train.mid')
# 选择第7个轨道（索引为6）
track = midi.tracks[6]


# 初始化列表和字典
notes = []  # 用于存储音符信息（开始时间、持续时间、音高）
active = {}  # 用于记录当前正在演奏的音符
current_time = 0.0  # 当前时间，用于计算音符的开始和持续时间
# 遍历轨道中的所有消息
for msg in track:
    # 更新当前时间，如果消息有时间属性
    current_time += msg.time if msg.time else 0.0
    # 处理音符开始消息
    if msg.type == 'note_on' and msg.velocity > 0:
        # 记录音符的开始时间，使用通道和音高作为键
        active[(msg.channel, msg.note)] = current_time
    # 处理音符结束消息（note_off或velocity为0的note_on）
    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
        # 创建键来查找音符
        key = (msg.channel, msg.note)
        # 如果音符在活动字典中，则计算其持续时间并添加到notes列表
        if key in active:
            start = active.pop(key)  # 获取开始时间并从活动字典中移除
            notes.append((start, current_time - start, msg.note))  # 添加（开始时间、持续时间、音高）

# 打印音符总数
print('notes', len(notes))
# 打印前80个音符的详细信息
for item in notes[:80]:
    print(item)

# 统计每个音高出现的次数
pitch_counter = Counter(note[2] for note in notes)
# 打印音高统计结果
print('pitch_counter', pitch_counter)
