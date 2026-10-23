async page => {
  await page.getByRole('button', {name:'取消',exact:true}).click();
  const text = page.getByRole('textbox',{name:'第1条字幕',exact:true});
  await text.fill('你好世界欢迎使用');
  await text.press('Home');
  await text.press('ArrowRight');
  await text.press('ArrowRight');
  await page.getByRole('button',{name:'拆分',exact:true}).click();
  if(await text.inputValue() !== '你好') throw new Error('split failed');
  await page.getByRole('button',{name:'合并下一条',exact:true}).click();
  if(await text.inputValue() !== '你好世界欢迎使用') throw new Error('merge failed');
  await page.getByRole('button',{name:'＋ 导入视频 / 音频',exact:true}).click();
  await page.getByRole('textbox',{name:'文件路径',exact:true}).fill('output/test-video.mp4');
  await page.getByRole('button',{name:'确定',exact:true}).click();
  await page.getByText('素材已导入',{exact:true}).waitFor();
  await page.getByRole('button',{name:'确认并记住断句 →',exact:true}).click();
  await page.getByRole('button',{name:'确认学习',exact:true}).click();
  await page.getByText('已记住这份成稿的断句',{exact:true}).waitFor();
  await page.getByRole('button',{name:'◈ 断句习惯',exact:true}).click();
  await page.getByText('4 条 · 已学习',{exact:true}).waitFor();
  await page.screenshot({path:'output/playwright/memory.png',fullPage:true});
  await page.getByRole('button',{name:'▤ 字幕编辑',exact:true}).click();
  await page.screenshot({path:'output/playwright/editor.png',fullPage:true});
  console.log('UI_SMOKE_OK: edit, split, merge, import media, learn confirmed draft, memory persisted');
}
