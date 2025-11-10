import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

def check_token_contract(contract_info: str) -> str:
    """检查Token合约创建时间"""
    try:
        # 解析输入：期望格式为 "address,network"
        parts = contract_info.split(',')
        if len(parts) != 2:
            return "Please provide: contract_address,network (e.g., 0x123...,ethereum)"
        
        address, network = parts[0].strip(), parts[1].strip()
        
        # 这里需要配置不同网络的RPC
        base_urls = {
            'ethereum': 'https://api.etherscan.io/v2/api',
            'bsc': 'https://api.etherscan.io/v2/api',
            'polygon': 'https://api.polygonscan.coam/v2/api'
        }
        chains = {
            'ethereum': "1",
            'bsc': "56",
            'polygon': "137"
        }
        url = base_urls[network]
        # # 第一步：获取合约创建信息（包含创建者地址、交易哈希等）
        # params = {
        #     "module": "contract",
        #     "action": "getcontractcreation",
        #     "contractaddresses": address,
        #     "apikey": ETHERSCAN_API_KEY,
        #     "chain": chains[network]
        # }
        # resp = requests.get(url, params=params)
        # data = resp.json()
        # if data["status"] != "1" or not data["result"]:
        #     raise ValueError(f"查询失败: {data.get('message', 'unknown error')}")

        # creation_tx_hash = data["result"][0]["txHash"]
        # print(f"创建交易哈希: {creation_tx_hash}")

        # # 第二步：获取交易详情，找到对应区块号
        # params = {
        #     "module": "proxy",
        #     "action": "eth_getTransactionByHash",
        #     "txhash": creation_tx_hash,
        #     "apikey": ETHERSCAN_API_KEY
        # }
        # resp = requests.get(url, params=params, proxies="http://127.0.0.1:7890")
        # tx_data = resp.json()
        # block_number = int(tx_data["result"]["blockNumber"], 16)

        querystring = {"apikey":ETHERSCAN_API_KEY,"chainid":chains[network],"module":"contract","action":"getcontractcreation","contractaddresses":address}
        resp = requests.get(url, params=querystring, proxies={"http":"http://127.0.0.1:7890", "https":"http://127.0.0.1:7890"})
        data = resp.json()
        print(data)
        creation_time = datetime.utcfromtimestamp(data["result"])
        return creation_time
    except Exception as e:
        return f"Error: {str(e)}"



if __name__ == "__main__":
    contract_info = "0x38B145C0C028DCf9B1D856687E72034c33444444,bsc"
    creation_time = check_token_contract(contract_info)
    print(f"合约创建时间 (UTC): {creation_time}")