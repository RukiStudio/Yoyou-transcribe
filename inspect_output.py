# 导入必要的库
from pathlib import Path  # 用于处理文件路径
from mido import MidiFile  # 用于处理MIDI文件



# 打开并读取MIDI文件
midi = MidiFile('music_transcriber_outputs/test_output.mid')  # 创建MIDI文件对象
# 打印MIDI文件中的轨道数量
print('tracks', len(midi.tracks))
# 遍历每个轨道
for i, track in enumerate(midi.tracks):
    name = ''  # 初始化轨道名称
    msgs = []  # 初始化消息列表
    # 遍历轨道中的每条消息
    for msg in track:
        # 如果消息类型是轨道名称，则更新轨道名称
        if msg.type == 'track_name':
            name = msg.name
        # 如果消息类型是音符开启或关闭，则将其添加到消息列表中
        if msg.type in {'note_on','note_off'}:
            msgs.append((msg.type, msg.channel, msg.note, msg.time, msg.velocity))
    # 打印轨道信息
    print('track', i, name, 'note_events', len(msgs))
    # 打印前20条音符消息
    for item in msgs[:20]:
        print(' ', item)
    # 打印空行分隔不同轨道
    print()
