async page => {
  const text = page.getByRole('textbox', {name: '第1条字幕', exact: true});
  await text.fill('戰略之助動力電池\nAI 技術');
  const start = await page.getByRole('spinbutton', {name: '第1条开始秒数', exact: true}).inputValue();
  const end = await page.getByRole('spinbutton', {name: '第1条结束秒数', exact: true}).inputValue();
  await page.getByRole('button', {name: '繁转简', exact: true}).click();
  await page.getByText('全部字幕已转为简体，时间与断句保持不变，可撤销', {exact: true}).waitFor();
  if (await text.inputValue() !== '战略之助动力电池\nAI 技术') throw new Error('conversion failed');
  if (await page.getByRole('spinbutton', {name: '第1条开始秒数', exact: true}).inputValue() !== start) throw new Error('start changed');
  if (await page.getByRole('spinbutton', {name: '第1条结束秒数', exact: true}).inputValue() !== end) throw new Error('end changed');
  await page.getByRole('button', {name: '↶ 撤销', exact: true}).click();
  if (await text.inputValue() !== '戰略之助動力電池\nAI 技術') throw new Error('undo failed');
  await page.getByRole('button', {name: '繁转简', exact: true}).click();
  await page.waitForFunction(() => document.querySelector('.cue-row textarea')?.value === '战略之助动力电池\nAI 技术');
  await page.getByText('已自动保存', {exact: true}).waitFor();
  await page.reload();
  await page.getByText('已自动保存', {exact: true}).waitFor({state: 'hidden'});
  await text.waitFor();
  if (await text.inputValue() !== '战略之助动力电池\nAI 技术') throw new Error('save/reload failed');
  console.log('SIMPLIFY_UI_OK: conversion, timings, undo, autosave, reload');
}
