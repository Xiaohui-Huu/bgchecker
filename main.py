# background_check_agent.py
import os
import json
import requests
import httpx
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_classic.tools import Tool
from langchain_openai import ChatOpenAI
from langchain_classic.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_classic.schema import SystemMessage
from langchain_community.utilities import SerpAPIWrapper
from bs4 import BeautifulSoup
from web3 import Web3

from github import aggregate_github_project



load_dotenv(override=True)
model = "google/gemini-2.5-flash-lite-preview-09-2025"
url = 'https://openrouter.ai/api/v1'
TEMPERATURE = 0.4
MAX_TOKENS = 600000
os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

class BackgroundCheckAgent:
    def __init__(self, openai_api_key: str, serp_api_key: Optional[str] = None):
        """初始化背景调查Agent"""
        self.openai_api_key = openai_api_key
        self.serp_api_key = serp_api_key
        
        # client = httpx.Client(proxy="http://127.0.0.1:7890")

        # 初始化LLM
        self.llm = ChatOpenAI(
            model=model,
            api_key=openai_api_key,
            openai_api_base=url,
            # client=client
        )
        
        # 初始化工具
        self.tools = self._create_tools()
        
        # 创建Agent
        self.agent = self._create_agent()
        
    def _create_tools(self) -> List[Tool]:
        """创建所有需要的工具"""
        tools = [
            Tool(
                name="scrape_website",
                func=self._scrape_website,
                description="抓取网站内容，用于查找Terms of Use和Privacy Policy等信息。输入：URL，输出：网页文本内容"
            ),
            Tool(
                name="analyze_legal_entities",
                func=self._analyze_legal_entities,
                description="使用AI分析项目的法律实体。输入：Terms of Use和Privacy Policy的URL或内容，输出：识别的法律实体信息"
            ),
            Tool(
                name="search_company_info",
                func=self._search_company_info,
                description="在Google搜索公司信息。输入：公司名称和地区，输出：公司简介"
            ),
            # Tool(
            #     name="scrape_linkedin",
            #     func=self._scrape_linkedin,
            #     description="获取LinkedIn上的团队信息。输入：LinkedIn公司页面URL，输出：团队成员列表"
            # ),
            Tool(
                name="scrape_twitter",
                func=self._scrape_twitter,
                description="获取Twitter/X上的团队成员。输入：Twitter handle，输出：相关团队成员"
            ),
            Tool(
                name="check_github_repo",
                func=self._check_github_repo,
                description="检查GitHub仓库所有权。输入：github repo owner和repo name，输出：仓库所有者信息和贡献者信息"
            ),
            Tool(
                name="check_token_contract",
                func=self._check_token_contract,
                description="检查Token合约创建时间。输入：合约地址和区块链网络，输出：创建时间"
            ),
            Tool(
                name="search_funding_rounds",
                func=self._search_funding_rounds,
                description="搜索项目融资信息。输入：项目名称，输出：融资轮次信息"
            ),
            Tool(
                name="check_coinmarketcap",
                func=self._check_coinmarketcap,
                description="在CoinMarketCap查询Token上架信息。输入：Token名称或符号，输出：上架的交易所列表"
            ),
            Tool(
                name="analyze_project_risks",
                func=self._analyze_project_risks,
                description="使用AI分析项目风险和争议。输入：项目名称列表，输出：风险分析报告"
            ),
            Tool(
                name="analyze_venture_risks",
                func=self._analyze_venture_risks,
                description="使用AI分析投资机构风险。输入：机构名称列表，输出：风险和制裁信息"
            )
        ]
        return tools
    
    def _scrape_website(self, url: str) -> str:
        """抓取网站内容"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            # 移除script和style标签
            for script in soup(["script", "style"]):
                script.decompose()
            
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text[:5000]  # 限制长度
        except Exception as e:
            return f"Error scraping {url}: {str(e)}"
    
    def _analyze_legal_entities(self, content: str) -> str:
        """使用LLM分析法律实体"""
        prompt = f"""
        Based on the following Terms of Use and Privacy Policy content, 
        identify all legal entities associated with this project:
        
        {content}
        
        Please provide:
        1. Company names
        2. Registered addresses
        3. Registration numbers (if available)
        4. Jurisdictions
        """
        
        response = self.llm.invoke(prompt)
        return response.content
    
    def _search_company_info(self, query: str) -> str:
        """搜索公司信息"""
        if self.serp_api_key:
            search = SerpAPIWrapper(serpapi_api_key=self.serp_api_key)
            return search.run(query)
        else:
            # 使用DuckDuckGo作为替代
            from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
            search = DuckDuckGoSearchAPIWrapper()
            return search.run(query)
    
    # def _scrape_linkedin(self, url: str) -> str:
    #     """获取LinkedIn信息（需要处理登录限制）"""
    #     # LinkedIn有反爬虫机制，需要用官方API或第三方服务
    #     return "LinkedIn scraping requires authentication. Please use LinkedIn API or manual review."
    
    def _scrape_twitter(self, handle: str) -> str:
        """获取Twitter信息"""
        # 需要使用Twitter API V2
        return f"To get Twitter data for @{handle}, please use Twitter API v2 with proper authentication."
    
    def _check_github_repo(self, github_repo_owner: str, github_repo_name: str) -> str:
        """检查GitHub仓库"""
        data = aggregate_github_project(github_repo_owner, github_repo_name, token=GITHUB_TOKEN)
        with open("github_project_data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return data
        # try:
        #     api_url = f"https://api.github.com/search/repositories?q={project_name}"
        #     headers = {'Accept': 'application/vnd.github.v3+json'}
            
        #     response = requests.get(api_url, headers=headers)
        #     if response.status_code == 200:
        #         data = response.json()
        #         if data['items']:
        #             repo = data['items'][0]
        #             return json.dumps({
        #                 'name': repo['name'],
        #                 'owner': repo['owner']['login'],
        #                 'created_at': repo['created_at'],
        #                 'url': repo['html_url']
        #             }, indent=2)
        #     return "No repository found"
        # except Exception as e:
        #     return f"Error: {str(e)}"
    
    def _check_token_contract(self, contract_info: str) -> str:
        """检查Token合约创建时间"""
        try:
            # 解析输入：期望格式为 "address,network"
            parts = contract_info.split(',')
            if len(parts) != 2:
                return "Please provide: contract_address,network (e.g., 0x123...,ethereum)"
            
            address, network = parts[0].strip(), parts[1].strip()
            
            # 这里需要配置不同网络的RPC
            base_urls = {
                'ethereum': 'https://api.etherscan.io/api',
                'bsc': '"https://api.bscscan.com/api"',
                'polygon': 'https://api.polygonscan.com/api'
            }
            url = base_urls[network]
            # 第一步：获取合约创建信息（包含创建者地址、交易哈希等）
            params = {
                "module": "contract",
                "action": "getcontractcreation",
                "contractaddresses": address,
                "apikey": ETHERSCAN_API_KEY
            }
            resp = requests.get(url, params=params)
            data = resp.json()
            if data["status"] != "1" or not data["result"]:
                raise ValueError(f"查询失败: {data.get('message', 'unknown error')}")

            creation_tx_hash = data["result"][0]["txHash"]
            print(f"创建交易哈希: {creation_tx_hash}")

            # 第二步：获取交易详情，找到对应区块号
            params = {
                "module": "proxy",
                "action": "eth_getTransactionByHash",
                "txhash": creation_tx_hash,
                "apikey": ETHERSCAN_API_KEY
            }
            resp = requests.get(url, params=params)
            tx_data = resp.json()
            block_number = int(tx_data["result"]["blockNumber"], 16)

            # 第三步：查询区块时间戳
            params = {
                "module": "proxy",
                "action": "eth_getBlockByNumber",
                "tag": hex(block_number),
                "boolean": "true",
                "apikey": ETHERSCAN_API_KEY
            }
            resp = requests.get(url, params=params)
            block_data = resp.json()
            timestamp = int(block_data["result"]["timestamp"], 16)

            creation_time = datetime.utcfromtimestamp(timestamp)
            print(f"合约创建时间 (UTC): {creation_time}")
            return creation_time
            
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _search_funding_rounds(self, project_name: str) -> str:
        """搜索融资信息"""
        query = f"{project_name} funding rounds investment Series A B C"
        return self._search_company_info(query)
    
    def _check_coinmarketcap(self, token: str) -> str:
        """查询CoinMarketCap"""
        # 需要CoinMarketCap API密钥
        cmc_api_key = os.getenv('CMC_API_KEY')
        if not cmc_api_key:
            return "CoinMarketCap API key not configured"
        
        try:
            url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
            headers = {
                'Accepts': 'application/json',
                'X-CMC_PRO_API_KEY': cmc_api_key,
            }
            params = {'symbol': token}
            
            response = requests.get(url, headers=headers, params=params)
            data = response.json()
            
            if 'data' in data:
                return json.dumps(data['data'], indent=2)
            return "Token not found"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _analyze_project_risks(self, projects: str) -> str:
        """分析项目风险"""
        prompt = f"""
        Analyze the current status and identify any controversies or risks for these projects:
        {projects}
        
        Please provide:
        1. Current operational status
        2. Historical controversies
        3. Risk factors
        4. Any failures or shutdowns
        """
        
        response = self.llm.invoke(prompt)
        return response.content
    
    def _analyze_venture_risks(self, ventures: str) -> str:
        """分析投资机构风险"""
        prompt = f"""
        Analyze the current status and identify any sanctions, investigations, 
        controversies, or risks for these venture firms/entities:
        {ventures}
        
        Please provide:
        1. Current status
        2. Any sanctions or regulatory actions
        3. Investigations or legal issues
        4. Controversies and reputation risks
        """
        
        response = self.llm.invoke(prompt)
        return response.content
    
    def _create_agent(self) -> AgentExecutor:
        """创建Agent执行器 - 使用新的 tool calling 格式"""
        
        # 使用新的 prompt 格式（与 tool calling 兼容）
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a professional blockchain project background check agent.
Your task is to conduct thorough due diligence on crypto projects by:

1. Identifying project legal entities
2. Finding UBOs and key stakeholders  
3. Analyzing team members and their history
4. Checking smart contract information
5. Investigating funding and listings
6. Assessing risks and controversies

Use the available tools systematically to gather all required information.
Be thorough and cite sources when possible."""),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # 使用 create_tool_calling_agent 而不是 create_openai_functions_agent
        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=20,
            handle_parsing_errors=True,
            return_intermediate_steps=True  # 有助于调试
        )
        
        return agent_executor
    
    def run_full_check(self, project_info: Dict) -> Dict:
        """执行完整的背景调查"""
        results = {}
        
        # No.1 - 项目实体
        print("\n=== Checking Project Entities ===")
        query = f"""
        For the project with website {project_info.get('website', '')}, 
        find and analyze the Terms of Use and Privacy Policy to identify legal entities.
        """
        results['entities'] = self.agent.invoke({"input": query})
        
        # No.2-4 - UBOs和团队成员
        print("\n=== Checking Team and UBOs ===")
        query = f"""
        For project {project_info.get('name', '')}, 
        find team members, founders, and UBOs from:
        1. Official website team page
        2. LinkedIn company page: {project_info.get('linkedin', '')}
        3. Twitter/X account: {project_info.get('twitter', '')}
        """
        results['team'] = self.agent.invoke({"input": query})
        
        # No.5 - 合约
        print("\n=== Checking Smart Contracts ===")
        query = f"""
        For token contract {project_info.get('contract_address', '')}, 
        check when it was deployed, who is the creator, and whether the contract is verified.
        """
        results['contracts'] = self.agent.invoke({"input": query})
        
        # No.6 - GitHub开发
        print("\n=== Checking GitHub Development ===")
        query = f"""
        For project {project_info.get('github_repo_name', '')}, 
        check the creators and developers to determine if it's developed in-house or by third party.
        """
        results['github'] = self.agent.invoke({"input": query})

        # No.10-11 - 上架和融资
        print("\n=== Checking Listings and Funding ===")
        query = f"""
        For token {project_info.get('token_symbol', '')}, 
        check where it's listed on CoinMarketCap and search for funding round information.
        """
        results['listings'] = self.agent.invoke({"input": query})
        
        # No.31 - 历史项目
        print("\n=== Checking Team History ===")
        query = f"""
        Check if key team members have founded or led any failed projects in the past.
        """
        results['history'] = self.agent.invoke({"input": query})
        
        # No.36 - 关联风险
        print("\n=== Checking Associated Risks ===")
        query = f"""
        Analyze if the project or team is associated with any entities or individuals 
        that pose reputation or consumer risks.
        """
        results['risks'] = self.agent.invoke({"input": query})
        
        return results
    
    def generate_report(self, results: Dict, output_file: str = "background_check_report.json"):
        """生成调查报告"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'results': results
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\nReport saved to {output_file}")
        return report


# 使用示例
if __name__ == "__main__":
    # 配置
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    SERP_API_KEY = os.getenv("SERP_API_KEY")  # 可选
    
    # 创建Agent
    agent = BackgroundCheckAgent(OPENAI_API_KEY, SERP_API_KEY)
    
    # 项目信息
    project_info = {
        'name': 'Kerberus',
        'website': 'https://www.kerberus.com/',
        'linkedin': 'https://www.linkedin.com/company/kerberus-inc',
        'twitter': 'https://x.com/Kerberus',
        'github_repo_owner': 'projectkerberus',
        'github_repo_name': 'terraform-kerberus-crossplane',
        'token_symbol': 'Kerberus',
        'contract_address': '0x38B145C0C028DCf9B1D856687E72034c33444444,bsc',  # 实际合约地址
        'network': 'bsc'
    }
    
    # 执行完整检查
    results = agent.run_full_check(project_info)
    
    # 生成报告
    agent.generate_report(results)