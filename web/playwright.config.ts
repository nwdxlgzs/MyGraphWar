import{defineConfig}from"@playwright/test";
export default defineConfig({testDir:"./e2e",timeout:45000,retries:0,use:{baseURL:"http://127.0.0.1:8000",headless:true,viewport:{width:1440,height:900}},webServer:{command:"python ../run.py",url:"http://127.0.0.1:8000/api/v1/health",reuseExistingServer:false,timeout:30000},reporter:"line"});
