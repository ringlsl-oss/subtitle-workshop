async page => {
  await page.getByRole('button',{name:'＋ 导入视频 / 音频',exact:true}).click();
  await page.getByRole('textbox',{name:'文件路径',exact:true}).fill('output/chinese.wav');
  await page.getByRole('button',{name:'确定',exact:true}).click();
  await page.getByText(/chinese.wav · 音频/).waitFor({state:'attached'});
  await page.getByRole('button',{name:'查看 / 编辑文稿',exact:true}).click();
  await page.getByRole('textbox',{name:'文稿正文',exact:true}).fill('你好欢迎使用字幕工房。我们一起学习你的断句习惯，让字幕更符合说话的节奏。');
  await page.getByRole('button',{name:'保存文稿',exact:true}).click();
  await page.getByRole('button',{name:'自动识别',exact:true}).click();
  await page.getByText(/已关联文稿：/).waitFor();
  await page.getByRole('button',{name:'开始识别',exact:true}).click();
  await page.getByRole('button',{name:'使用这套规则识别',exact:true}).click();
  await page.getByRole('heading',{name:'文稿与语音核对',exact:true}).waitFor({timeout:120000});
  await page.getByRole('checkbox',{name:'采用这条文稿文字，保留原时间',exact:true}).waitFor();
  await page.getByRole('button',{name:'试听这句',exact:true}).first().click();
  await page.waitForFunction(()=>document.getElementById('video').currentTime>0);
  await page.screenshot({path:'output/playwright/reference-recognition.png',fullPage:true});
  await page.getByRole('button',{name:'取消',exact:true}).click();
  if(!(await page.getByRole('textbox',{name:'第1条字幕',exact:true}).inputValue()).includes('工坊'))throw new Error('Reference silently changed independent recognition');
  await page.getByText('已自动保存',{exact:true}).waitFor();
  console.log('REFERENCE_ASR_UI_OK: real small Chinese recognition, automatic comparison, reference did not bias recognition, audio audition');
}
