"use strict";
const copy={
 en:{eyebrow:"QMINMU'S PERSONAL LIBRARY",title:'Pages worth keeping.',intro:'Course notes, lab handouts, and exam resources.<br>A small archive for learning, one course at a time.',courses:'COURSES',collection:'COURSE COLLECTION',asideNote:'Original files, organized by course.',format:'PDF COLLECTION',footer:'Collected by QMInmu. Made for revisiting.',emptyTitle:'No matching pages.',emptyText:'Try another filename or choose a different category.',all:'All materials',search:'Search filenames…',open:'Open ↗',download:'Download ↓',files:'files',pages:'pages',course:'course',coursePlural:'courses',storage:'of materials',results:n=>`${n} ${n===1?'file':'files'}`},
 zh:{eyebrow:'QMINMU 的个人学习资料库',title:'书页之间，慢慢积累。',intro:'讲义、课件、教材与试题。<br>按课程收藏，留给每一次回顾。',courses:'课程目录',collection:'课程资料',asideNote:'按课程归档，保留原文件。',format:'PDF 资料',footer:'由 QMInmu 收藏整理，便于日后重温。',emptyTitle:'没有找到匹配的资料',emptyText:'试试其他文件名，或选择不同的资料类别。',all:'全部资料',search:'搜索文件名…',open:'打开 ↗',download:'下载 ↓',files:'份资料',pages:'页',course:'门课程',coursePlural:'门课程',storage:'资料大小',results:n=>`${n} 份资料`}
};
let catalog,course,category='all';
let lang='en';
try{if(localStorage.getItem('marginalia-language')==='zh')lang='zh'}catch{}
const $=id=>document.getElementById(id);
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
const size=bytes=>`${(bytes/1024/1024).toFixed(bytes>=10485760?1:2)} MiB`;
function selectCourse(id){course=catalog.courses.find(c=>c.id===id)||catalog.courses[0];category='all';$('search').value='';render()}
function render(){
 if(!catalog||!course)return;
 const t=copy[lang];document.documentElement.lang=lang==='en'?'en':'zh-CN';
 document.querySelectorAll('[data-i18n]').forEach(n=>{if(n.dataset.i18n==='intro')n.innerHTML=t.intro;else n.textContent=t[n.dataset.i18n]});
 $('language').textContent=lang==='en'?'中文':'English';$('language').setAttribute('aria-label',lang==='en'?'切换为中文':'Switch to English');
 $('search').placeholder=t.search;$('search').setAttribute('aria-label',t.search);
 $('filters').setAttribute('aria-label',lang==='en'?'Material categories':'资料类别');
 const total=catalog.courses.flatMap(c=>c.files);
 $('stats').replaceChildren(...[[catalog.courses.length,catalog.courses.length===1?t.course:t.coursePlural],[total.length,t.files],[size(total.reduce((a,f)=>a+f.bytes,0)),t.storage]].map(([n,label])=>{const s=el('span');s.append(el('strong',null,n),document.createTextNode(label));return s}));
 $('course-list').replaceChildren(...catalog.courses.map((c,i)=>{const b=el('button','course-button');b.type='button';b.setAttribute('aria-pressed',String(c.id===course.id));b.append(el('span','number',String(i+1).padStart(2,'0')),el('span','name',c.name[lang]),el('span','sub',`${c.name[lang==='en'?'zh':'en']} · ${c.files.length} PDF`));b.addEventListener('click',()=>selectCourse(c.id));return b}));
 $('course-title').textContent=course.name[lang];$('course-subtitle').textContent=course.name[lang==='en'?'zh':'en'];$('course-description').textContent=course.description[lang];
 $('filters').replaceChildren(...[{id:'all',name:{en:copy.en.all,zh:copy.zh.all}},...course.categories].map(c=>{const b=el('button','filter',c.name[lang]);b.type='button';b.dataset.category=c.id;b.setAttribute('aria-pressed',String(category===c.id));b.append(el('span',null,c.id==='all'?course.files.length:course.files.filter(f=>f.category===c.id).length));b.addEventListener('click',()=>{category=c.id;render()});return b}));
 renderFiles();
}
function renderFiles(){
 if(!course)return;
 const t=copy[lang],query=$('search').value.trim().toLocaleLowerCase();
 const files=course.files.filter(f=>(category==='all'||f.category===category)&&f.name.toLocaleLowerCase().includes(query));
 $('result-count').textContent=t.results(files.length);$('empty').hidden=files.length!==0;
 $('materials').replaceChildren(...files.map(f=>{
  const row=el('article','material');row.dataset.filename=f.name;
  const icon=el('div','file-icon');icon.setAttribute('aria-hidden','true');icon.append(el('span',null,'PDF'));
  const body=el('div','file-body'),href=encodeURI(f.path);
  const name=el('a','file-name',f.name);name.href=href;name.target='_blank';name.rel='noopener noreferrer';
  const meta=el('div','file-meta');meta.append(el('span',null,course.categories.find(c=>c.id===f.category).name[lang]),el('span',null,`${f.pages} ${t.pages}`),el('span',null,size(f.bytes)));body.append(name,meta);
  const actions=el('div','file-actions');const open=el('a','open-link',t.open);open.href=href;open.target='_blank';open.rel='noopener noreferrer';open.setAttribute('aria-label',`${lang==='en'?'Open':'打开'} ${f.name}`);
  const download=el('a','download-link',t.download);download.href=href;download.download=f.name;download.setAttribute('aria-label',`${lang==='en'?'Download':'下载'} ${f.name}`);actions.append(open,download);row.append(icon,body,actions);return row;
 }));
}
$('language').addEventListener('click',()=>{lang=lang==='en'?'zh':'en';try{localStorage.setItem('marginalia-language',lang)}catch{}render()});
$('search').addEventListener('input',renderFiles);
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){e.preventDefault();$('search').focus()}});
fetch('catalog.json').then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(data=>{catalog=data;selectCourse(data.courses[0].id)}).catch(error=>{$('load-error').hidden=false;console.error('Catalog could not be loaded',error)});
