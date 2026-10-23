from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

store=core.Store(Path(__file__).resolve().parents[1]/'output'/'clarity-data')
p=core.new_profile('默认习惯','default')
core.learn(p,[{'start':0,'end':2,'text':'我们一起出发'},{'start':2,'end':4,'text':'去看看世界'},{'start':4,'end':6,'text':'让生活更美好'}],'历史成稿.srt')
empty=core.new_profile('宣传片','promo')
store.write('profiles.json',[p,empty])
project=core.new_project()
project['name']='断句习惯验证'
project['profile_id']='promo'
project['cues']=[{'start':0,'end':10,'text':'我们一起出发，去看看世界，让生活更美好。'}]
project['original_cues']=project['cues']
store.save_project(project)
