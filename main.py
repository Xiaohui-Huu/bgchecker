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
model = "x-ai/grok-4-fast"
url = 'https://openrouter.ai/api/v1'
TEMPERATURE = 0.2
MAX_TOKENS = 600000
# os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
# os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

class BackgroundCheckAgent:
    def __init__(self, openai_api_key: str, serp_api_key: Optional[str] = None, project_name: str = ''):
        """初始化背景调查Agent"""
        self.openai_api_key = openai_api_key
        self.serp_api_key = serp_api_key
        self.output_file = os.path.join(os.getcwd(), f"results/{project_name}.md")
        self._initialize_output_file()

        self.llm = ChatOpenAI(
            model=model,
            api_key=openai_api_key,
            openai_api_base=url,
            # client=client
        )
        
        self.tools = self._create_tools()
        
        self.agent = self._create_agent()
        
    def _create_tools(self) -> List[Tool]:
        """创建所有需要的工具"""
        tools = [
            Tool(
                name="extensively_infomation_and_data",
                func=self._search_realted_infomation_and_data,
                description="广泛搜索相关信息和数据。输入：项目名称，项目网站，项目X账号，搜索目标。输出：相关信息和数据"
            ),
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
                name="check_token_contracts",
                func=self._check_token_contracts,
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

    def _initialize_output_file(self):
        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(f"# LLM Outputs ({datetime.now().isoformat()})\n\n")

    def _log_llm_output(self, label: str, content: str):
        if not content:
            return
        with open(self.output_file, "a", encoding="utf-8") as f:
            f.write(f"## {label}\n")
            f.write(content.strip() + "\n\n")

    def _invoke_llm(self, prompt: str, label: str) -> str:
        response = self.llm.invoke(prompt)
        content = getattr(response, "content", str(response))
        self._log_llm_output(label, content)
        return content

    def _extract_agent_output(self, agent_response):
        if isinstance(agent_response, dict):
            output = agent_response.get("output")
            if output:
                return output
            return json.dumps(agent_response, ensure_ascii=False, indent=2)
        return str(agent_response)
    def _search_realted_infomation_and_data(self, query: str) -> str:
        """广泛搜索相关信息和数据"""
        query = f"""
        Targeting {query}, search all networks to collect related information and data.
        """
        try:
            if self.serp_api_key:
                search = SerpAPIWrapper(serpapi_api_key=self.serp_api_key)
                return search.run(query)
            else:
                # 使用DuckDuckGo作为替代
                from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
                search = DuckDuckGoSearchAPIWrapper()
                return search.run(query)
        except Exception as e:
            return f"Error searching {query}: {str(e)}, you need to change searching keywords and try again."

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
            
            return text[:5000]
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
        
        return self._invoke_llm(prompt, "Legal Entities Analysis")
    
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
    
    def _check_token_contracts(self, contract_infos: List[str]) -> str:
        """检查Token合约创建时间"""
        try:
            # 解析输入：期望格式为 "address,network"
            creation_times = []
            for contract_info in contract_infos:
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

                timestamp = data["result"][0]["timestamp"]
                creation_time = datetime.utcfromtimestamp(timestamp)
                print(f"合约创建时间 (UTC): {creation_time}")
                creation_times.append(creation_time)
            return creation_times
                
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
        
        return self._invoke_llm(prompt, "Project Risks Analysis")
    
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
        
        return self._invoke_llm(prompt, "Venture Risks Analysis")
    
    def _create_agent(self) -> AgentExecutor:
        """创建Agent执行器 - 使用新的 tool calling 格式"""
        
        # 使用新的 prompt 格式（与 tool calling 兼容）
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a professional blockchain project background check agent.
For each information you collect, you MUST provide the accessible source and the timestamp.
Your task is to conduct thorough due diligence on crypto projects by:

1. Identifying project legal entities
2. Finding UBOs and key stakeholders, analyzing team members and their history to answer the following questions:
3. Checking sanction risks.
4. Checking Litigation risks.
5. Checking Financial risks.
6. Checking continuity risks.
7. Checking reputation risks.
8. Checking smart contract information
9. Investigating funding and listings
10. Assessing risks and controversies
Use the available tools systematically to gather all required information."""),
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
        self._log_llm_output("Project Entities", self._extract_agent_output(results['entities']))

        # No.2 - UBOs和团队成员
        print("\n=== Checking Team and UBOs ===")
        query = f"""
        For project {project_info.get('name', '')} with website {project_info.get('website', '')} and its asset {project_info.get('asset', '')}, 
        find team members, founders, and UBOs from:
        1. Official website team page
        2. LinkedIn company page: {project_info.get('linkedin', '')}
        3. Twitter/X account: {project_info.get('twitter', '')}
        4. Founders: {project_info.get('founders', '')}
        5. Broadly search for team members and founders using search_company_info tool
        6. Analyze searched results and answer the following questions:
        7. Analyzing team members and their history to answer the following questions:
            (1) What are the project entities?
            (2) Who are the UBOs, majority shareholders and/or asset controllers?
            (3) Who are the project’s key team and what are their backgrounds?
            (4) How long has each project team member been involved in the project?
            (5) How long has the asset been operating on mainnet? 
            (6) Is the asset being developed in house or by a third party?
            (7) What classification is the asset: Governance, Reward, Utility, Exchange, Security, Stablecoin...?
            (8) What blockchains or protocols is the asset compatible with?
            (9) Is the asset, or is its purpose, regulated?
            (10) Where is the asset currently listed?
        """
        results['team'] = self.agent.invoke({"input": query})
        self._log_llm_output("Team and UBOs", self._extract_agent_output(results['team']))

        # No.3 - Checking sanction risks
        print("\n=== Checking Sanction Risks ===")
        query = f"""
        For project {project_info.get('name', '')} with website {project_info.get('website', '')} and X account {project_info.get('twitter', '')}, 
        Founders: {project_info.get('founders', '')},
        broadly search for related news and articles to check if any of the UBOs or key team are specially designated persons (subject to sanctions controls).
        Analyze searched results and answer the following questions:
           4.1. Are any of the project's UBOs or key team specially designated persons? (subject to sanctions controls)
           4.2. Are any of the project entities, UBOs or majority shareholders located in a country subject to comprehensive sanctions?
           4.3. Are any of the project team (including development labor) located in a country subject to comprehensive sanctions?
           4.4. Has the project team facilitated or actively encouraged the development of a community or revenue in a country subject to comprehensive sanctions?
           4.5. Is any of the project’s infrastructure funded by a sanctioned entity?
        """
        results['sanction_risks'] = self.agent.invoke({"input": query})
        self._log_llm_output("Sanction Risks", self._extract_agent_output(results['sanction_risks']))

        # No.4 - Checking Litigation risks
        print("\n=== Checking Litigation Risks ===")
        query = f"""
        For project {project_info.get('name', '')} with website {project_info.get('website', '')} and X account {project_info.get('twitter', '')}, 
        Founders: {project_info.get('founders', '')},
        broadly search for related news and articles to check if any of the UBOs or key team have been subject to criminal or civil litigation involving money-laundering, terror financing, crimes of dishonesty or financial misconduct.
        Analyze searched results and answer the following questions:
            (1) Has any of the UBOs or key team been subject to criminal or civil litigation involving money-laundering, terror financing, crimes of dishonesty or financial misconduct?
            (2) Has any of the UBOs, majority shareholders or key team been subject to any other criminal or civil litigation?
        """
        results['litigation_risks'] = self.agent.invoke({"input": query})
        self._log_llm_output("Litigation Risks", self._extract_agent_output(results['litigation_risks']))

        # No.5 - Checking Financial risks
        print("\n=== Checking Financial Risks ===")
        query = f"""
        For project {project_info.get('name', '')} with website {project_info.get('website', '')} and X account {project_info.get('twitter', '')} and its asset {project_info.get('asset', '')}, 
        Founders: {project_info.get('founders', '')},
        broadly search for related news and articles to check related financial risks.
        Analyze searched results and answer the following questions:
            (1) Are any of the UBOs or key team Politically Exposed Persons?
            (2) Has any of the UBOs or key team been subject to allegations of money-laundering, terror financing, crimes of dishonesty or financial misconduct?
            (3) Has any of the UBOs, majority shareholders or key team been subject to bankruptcy or liens against assets in the past 10 years?
            (4) Is there any other evidence that the UBOs, majority shareholders or key team are or have previously been involved with illicit activity?
            (5) Is there evidence that the asset is used for high risk or illicit  activities, including carding websites, gambling or darknet markets?
            (6) Is there evidence that the asset has been used for money-laundering or terror financing?
            (7) Is the asset a privacy coin or have any privacy features?
        """
        results['financial_risks'] = self.agent.invoke({"input": query})
        self._log_llm_output("Financial Risks", self._extract_agent_output(results['financial_risks']))

        # No.6 - Checking Continuity risks
        print("\n=== Checking Continuity Risks ===")
        query = f"""
        For project {project_info.get('name', '')} with website {project_info.get('website', '')} and X account {project_info.get('twitter', '')}, 
        Founders: {project_info.get('founders', '')},
        broadly search for related news and articles to check related continuity risks.
        Analyze searched results and answer the following questions:
            (1) Has any of the UBOs or key team founded/led a project that has failed?
            (2) Has any of the UBOs or key team made misleading or deceptive statements about this or any other venture? 
            (3) Are there credible allegations that the project has failed to deliver or poorly developed core features of its promised use case?
            (4) Is there evidence that the project is no longer developed or has been abandoned?
        """
        results['continuity_risks'] = self.agent.invoke({"input": query})
        self._log_llm_output("Continuity Risks", self._extract_agent_output(results['continuity_risks']))

        # No.7 - Checking Reputation risks
        print("\n=== Checking Reputation Risks ===")
        query = f"""
        For project {project_info.get('name', '')} with website {project_info.get('website', '')} and X account {project_info.get('twitter', '')} and its asset {project_info.get('asset', '')}, 
        Founders: {project_info.get('founders', '')},
        broadly search (including X, Reddit, YouTube, etc.) for {project_info.get('name', '')}-related news and articles, especially reputation and consumer's complaints to check related reputation risks.
        Analyze searched results and answer the following questions:
            (1) Have any of the key team made any misleading or deceptive comments/statements regarding their personal or professional history?
            (2) Is the key team or project closely associated with any other projects, entities  or individuals that pose significant reputation and/or consumer risks?
            (3) Has the asset been subject to credible market manipulation allegations?
            (4) Has the project made misleading or deceptive statements to attract investors to the asset?
            (5) Are there credible allegations that the project/asset is a scam?
            (6) Are the key team subject to credible allegations that the project team have been involved in a scam or fraud?
            (7) Are there any other allegations against the key team that pose significant reputational and/or consumer risks?
            (8) Is there any other activity by the key team that poses any reputation and/or consumer risks?
        """
        results['reputation_risks'] = self.agent.invoke({"input": query})
        self._log_llm_output("Reputation Risks", self._extract_agent_output(results['reputation_risks']))


        # No.8 - 上架和融资
        print("\n=== Checking Listings and Funding ===")
        query = f"""
        For token {project_info.get('token_symbol', '')} belongs to project {project_info.get('name', '')}, 
        check where it's listed on CoinMarketCap and search for funding round information.
        """
        results['listings'] = self.agent.invoke({"input": query})
        self._log_llm_output("Listings and Funding", self._extract_agent_output(results['listings']))
        
        # No.9 - 关联风险
        print("\n=== Checking Associated Risks ===")
        query = f"""
        Analyze if the project or team is associated with any entities or individuals 
        that pose reputation or consumer risks.
        """
        results['risks'] = self.agent.invoke({"input": query})
        self._log_llm_output("Associated Risks", self._extract_agent_output(results['risks']))
        
        # No.10 - GitHub开发
        print("\n=== Checking GitHub Development ===")
        query = f"""
        For project repository {project_info.get('github_repo_name', '')} owned by {project_info.get('github_repo_owner', '')}, 
        check the creators and developers to determine if it's developed in-house or by third party.
        """
        results['github'] = self.agent.invoke({"input": query})
        self._log_llm_output("GitHub Development", self._extract_agent_output(results['github']))

        # No.11 - 合约
        if project_info.get('contract_address'):
            print("\n=== Checking Smart Contracts ===")
            query = f"""
            For token asset {project_info.get('asset', '')} on {project_info.get('network', '')}, 
            check when it was deployed, who is the creator, and whether the contract is verified.
            """
            results['contracts'] = self.agent.invoke({"input": query})
            self._log_llm_output("Smart Contracts", self._extract_agent_output(results['contracts']))

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
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    SERP_API_KEY = os.getenv("SERP_API_KEY")
    
    project_name = 'Astherus USDF'

    # 创建Agent
    agent = BackgroundCheckAgent(OPENROUTER_API_KEY, SERP_API_KEY, project_name)
    
    # 项目信息
    project_info = {
        'name': project_name,
        'website': 'https://www.asterdex.com',
        'github_repo_owner': 'Asther',
        'github_repo_name': 'asther-contract',
        'founders': {
            'Founder': {
                'name': 'Leonard',
                'X': 'https://x.com/Leonard_Aster'
            }
        },
        'asset': 'USDF'
    }
    
    # 执行完整检查
    results = agent.run_full_check(project_info)
    
    # 生成报告
    agent.generate_report(results)