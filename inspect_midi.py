# 导入必要的库
from pathlib import Path  # 用于处理文件路径
from mido import MidiFile  # 用于处理MIDI文件

# 加载MIDI文件
midi = MidiFile('train.mid')
# 打印MIDI文件中的音轨数量
print('tracks', len(midi.tracks))
# 遍历每个音轨
for i, track in enumerate(midi.tracks):
    # 打印音轨编号和名称（如果有的话）
    print('track', i, 'name', track.name if hasattr(track, 'name') else 'n/a')
    # 筛选出特定类型的消息：音符开始、音符结束、程序变化、音轨名称、速度设置、节拍
    msgs = [msg for msg in track if msg.type in {'note_on','note_off','program_change','track_name','set_tempo','time_signature'}]
    # 打印筛选后的消息数量
    print('  messages', len(msgs))
    # 打印前30条消息的详细信息
    for msg in msgs[:30]:
        print('   ', msg)
    # 打印空行，用于分隔不同音轨的信息
    print()
