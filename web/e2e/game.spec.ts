import{test,expect}from"@playwright/test";

test("注册到函数发射的完整浏览器流程",async({page})=>{
  const username=`e2e_${Date.now()}`;
  await page.goto("/");
  await page.getByRole("button",{name:"没有账号？注册"}).click();
  await page.getByPlaceholder("用户名").fill(username);
  await page.getByPlaceholder("密码（至少 8 位）").fill("playwright123");
  await page.getByRole("button",{name:"注册并进入"}).click();
  await expect(page.getByRole("heading",{name:"创建战场"})).toBeVisible();
  const emptyGame={bounds:[-25,25,-14.6104,14.6104],function_mode:"normal",obstacles:[],craters:[],units:[],current:null,next_units:[],turn:0,turn_deadline:null,resolving:false,finished:true,winner:"A"};
  await page.locator('input[type="file"]').setInputFiles({name:"replay.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify({version:1,initial:emptyGame,shots:[],final:emptyGame}))});await expect(page.getByText("比赛重放")).toBeVisible();await page.getByRole("button",{name:"← 返回大厅"}).click();
  await page.getByRole("button",{name:"创建房间"}).click();
  await expect(page.getByRole("heading",{name:"参战席位"})).toBeVisible();
  await page.getByLabel("坐标范围方式").selectOption("random");
  await expect(page.getByLabel("横轴半范围")).toBeDisabled();
  await page.getByLabel("坐标范围方式").selectOption("fixed");
  await page.getByLabel("横轴半范围").fill("7.5");
  await expect(page.getByLabel("横轴半范围")).toHaveValue("7.5");
  await page.getByRole("button",{name:"添加电脑"}).click();
  await expect(page.getByText("电脑 1")).toBeVisible();
  await page.getByRole("button",{name:"开始对局"}).click();
  await expect(page.getByText(/比赛将在 \d 秒后开始/)).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible({timeout:12000});
  await expect(page.getByText(/x=-7.5…7.5/)).toBeVisible();
  const sound=page.getByLabel("声音开关");await expect(sound).toContainText("声音");await sound.click();await expect(sound).toContainText("静音");await sound.click();
  const fire=page.getByRole("button",{name:"发射函数"});
  await expect(fire).toBeEnabled({timeout:15000});
  await page.locator("aside input").first().fill("0");
  await fire.click();
  await expect(page.getByText("结算中")).toBeVisible();
  await expect(page.getByText(/第 \d+ 回合/)).toBeVisible();
});

test("两个独立浏览器完成加入、准备、开局和聊天同步",async({browser})=>{
  const stamp=Date.now(),roomName=`双人战场_${stamp}`;
  const ownerContext=await browser.newContext(),guestContext=await browser.newContext();
  const owner=await ownerContext.newPage(),guest=await guestContext.newPage();
  async function register(page:any,name:string){await page.goto("/");await page.getByRole("button",{name:"没有账号？注册"}).click();await page.getByPlaceholder("用户名").fill(name);await page.getByPlaceholder("密码（至少 8 位）").fill("playwright123");await page.getByRole("button",{name:"注册并进入"}).click();await expect(page.getByRole("heading",{name:"创建战场"})).toBeVisible()}
  await register(owner,`owner_${stamp}`);await register(guest,`guest_${stamp}`);
  await owner.locator(".create input").first().fill(roomName);await owner.getByRole("button",{name:"创建房间"}).click();
  await expect(owner.getByRole("heading",{name:"参战席位"})).toBeVisible();
  await expect(guest.getByText(roomName)).toBeVisible({timeout:6000});await guest.getByText(roomName).click();
  await guest.getByRole("button",{name:"准备"}).click();await expect(guest.getByRole("button",{name:"取消准备"})).toBeVisible();
  await expect(owner.getByText("已准备")).toBeVisible();await owner.getByRole("button",{name:"开始对局"}).click();
  await expect(owner.getByText(/比赛将在 \d 秒后开始/)).toBeVisible();await expect(guest.getByText(/比赛将在 \d 秒后开始/)).toBeVisible();
  await expect(owner.locator("canvas")).toBeVisible({timeout:12000});await expect(guest.locator("canvas")).toBeVisible({timeout:12000});
  await guest.getByPlaceholder("房间聊天").fill("双端同步成功");await guest.getByRole("button",{name:"发送"}).click();await expect(owner.getByText("双端同步成功")).toBeVisible();
  await guest.evaluate(()=>(window as any).__mgwSocket.close());await expect(guest.getByText(/连接中断，正在第/)).toBeVisible({timeout:6000});await expect(guest.getByText("连接已恢复，状态已同步")).toBeVisible({timeout:12000});await expect(guest.locator("canvas")).toBeVisible();
  await ownerContext.close();await guestContext.close();
});

test("扩展规则极坐标模式可以在浏览器中开局并发射",async({page})=>{
  const username=`polar_${Date.now()}`;await page.goto("/");await page.getByRole("button",{name:"没有账号？注册"}).click();await page.getByPlaceholder("用户名").fill(username);await page.getByPlaceholder("密码（至少 8 位）").fill("playwright123");await page.getByRole("button",{name:"注册并进入"}).click();
  await page.locator(".create select").selectOption("ffa");await page.getByRole("button",{name:"创建房间"}).click();await page.getByRole("button",{name:"添加电脑"}).click();
  await page.getByLabel("函数模式").selectOption("polar");await expect(page.getByLabel("函数模式")).toHaveValue("polar");await page.getByRole("button",{name:"开始对局"}).click();await expect(page.locator("canvas")).toBeVisible({timeout:12000});
  const fire=page.getByRole("button",{name:"发射函数"});await expect(fire).toBeEnabled({timeout:18000});await page.locator("aside input").first().fill("400*theta");await fire.click();await expect(page.getByText("结算中")).toBeVisible();
});

test("扩展规则参数方程可以输入双表达式并发射",async({page})=>{
  const username=`param_${Date.now()}`;await page.goto("/");await page.getByRole("button",{name:"没有账号？注册"}).click();await page.getByPlaceholder("用户名").fill(username);await page.getByPlaceholder("密码（至少 8 位）").fill("playwright123");await page.getByRole("button",{name:"注册并进入"}).click();await page.locator(".create select").selectOption("ffa");await page.getByRole("button",{name:"创建房间"}).click();await page.getByRole("button",{name:"添加电脑"}).click();await page.getByLabel("函数模式").selectOption("parametric");await page.getByRole("button",{name:"开始对局"}).click();await expect(page.locator("canvas")).toBeVisible({timeout:12000});
  const fire=page.getByRole("button",{name:"发射函数"});await expect(fire).toBeEnabled({timeout:18000});const inputs=page.locator("aside input");await inputs.nth(0).fill("t");await inputs.nth(1).fill("0.25*t");await expect(page.getByText("表达式有效")).toBeVisible();await fire.click();await expect(page.getByText("结算中")).toBeVisible();
});
