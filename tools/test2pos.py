import os
import subprocess
import time
import signal
from multiprocessing import Process
import json
import sys
from pathlib import Path

#所有创建进程的pid
pid_list = []
port_start = 9000

def Clear():
    os.system("rm -fr /tmp/node0*")
# 创建私钥对
def CreateKey(count):
    key_list = []
    key_file = open("./key.md", "w")
    for index in range(count):
        pipeline = os.popen("../target/release/subkey generate --scheme ed25519")
        item = {}
        for i in range(4):
            line_str = pipeline.readline()
            if i == 0:
                item["secret_phrase"] = line_str[15:-14]
            elif i == 1:
                item["secret_key"] = line_str[21:-1]
            elif i == 2:
                item["ed25519_pk"] = line_str[21:-1]
            elif i == 3:
                item["ed25519_addr"] = line_str[21:-1]
                break
        pipeline.close()
        xxx = "../target/release/subkey inspect --scheme sr25519 '%s'"%item["secret_phrase"]
        pipeline = os.popen(xxx)
        for i in range(4):
            line_str = pipeline.readline()
            if i == 2:
                item["sr25519_pk"] = line_str[21:-1]
            elif i == 3:
                item["sr25519_addr"] = line_str[21:-1]
        pipeline.read()
        pipeline.close()
        #将key写入文件保存
        key_file.write("# test%02d\n"%(index+1))
        key_file.write("|name|value|\n")
        key_file.write("| --- | --- |\n")
        key_file.write("|secret_phrase|%s|\n"%item["secret_phrase"])
        key_file.write("|secret_key|%s|\n"%item["secret_key"])
        key_file.write("|ed25519_pk|%s|\n"%item["ed25519_pk"])
        key_file.write("|ed25519_addr|%s|\n"%item["ed25519_addr"])
        key_file.write("|sr25519_pk|%s|\n"%item["sr25519_pk"])
        key_file.write("|sr25519_addr|%s|\n"%item["sr25519_addr"])
        #构建返回值
        dic = {}
        dic["secret_phrase"] = item["secret_phrase"]
        dic["secret_key"] = item["secret_key"]
        dic["ed25519_pk"] = item["ed25519_pk"]
        dic["ed25519_addr"] = item["ed25519_addr"]
        dic["sr25519_pk"] = item["sr25519_pk"]
        dic["sr25519_addr"] = item["sr25519_addr"]
        key_list.append(dic)
    return key_list

#生成自定义创世文件
def CreateCustomSpec(args):
    os.system("""
    ../target/release/substrate \
    build-spec \
    --disable-default-bootnode \
    --chain staging \
    > ./customSpec.json \
    2>/dev/null
    """)
    file_spec = open("./customSpec.json", "r")
    json_obj = json.load(file_spec)
    file_spec = open("./customSpec.json", "w")
    # 配置链名称
    if "name" in args:
        json_obj["name"] = args["name"]
    # 配置链id
    if "id" in args:
        json_obj["id"] = args["id"]
    # 配置币
    if "coin_config" in args:
        json_obj["properties"] = args["coin_config"]
    # 配置账户资产
    json_obj["genesis"]["runtime"]["balances"]["balances"] = args["balances"]
    # 配置验证人
    #print(args["validators"])
    json_obj["genesis"]["runtime"]["staking"]["invulnerables"] = []
    for item in args["validators"]:
        json_obj["genesis"]["runtime"]["staking"]["invulnerables"].append(item[0]["sr25519_addr"])
    # 配置控制人，和抵押金额
    json_obj["genesis"]["runtime"]["staking"]["stakers"] = []
    for item in args["validators"]:
        json_obj["genesis"]["runtime"]["staking"]["stakers"].append([item[0]["sr25519_addr"], item[1]["sr25519_addr"], item[3], 'Validator'])
    # 配置验证人session
    json_obj["genesis"]["runtime"]["session"]["keys"] = []
    for item in args["validators"]:
        json_obj["genesis"]["runtime"]["session"]["keys"].append([item[0]["sr25519_addr"], item[0]["sr25519_addr"],{
              "grandpa": item[2]["ed25519_addr"],
              "babe": item[2]["sr25519_addr"],
              "im_online": item[2]["sr25519_addr"],
              "authority_discovery": item[2]["sr25519_addr"]
            }])
    # 配置议会
    json_obj["genesis"]["runtime"]["elections"]["members"] = []
    for item in args["elections"]:
        json_obj["genesis"]["runtime"]["elections"]["members"].append([item[0]["sr25519_addr"], item[1]])

    # 配置技术委员会
    json_obj["genesis"]["runtime"]["technicalCommittee"]["members"] = []
    for item in args["elections"]:
        json_obj["genesis"]["runtime"]["technicalCommittee"]["members"].append(item[0]["sr25519_addr"])

    # 配置社区成员
    json_obj["genesis"]["runtime"]["society"]["members"] = []
    for item in args["society"]:
        json_obj["genesis"]["runtime"]["society"]["members"].append(item["sr25519_addr"])
    
    # 设置sudo
    json_obj["genesis"]["runtime"]["sudo"]["key"] = args["sudo"]["sr25519_addr"]

    # 设置nft模块的owner
    json_obj["genesis"]["runtime"]["nft"]["superOwner"] = args["nft"]["sr25519_addr"]
    json_obj["genesis"]["runtime"]["nft"]["useSuperOwner"] = True
    json.dump(json_obj, file_spec, indent=2)
    file_spec.close()

# 创建创世文件的raw
def CreateRaw():
    os.system("../target/release/substrate build-spec --chain=./customSpec.json --raw --disable-default-bootnode > ./customSpecRaw.json 2>/dev/null")

def GetFirstNodeAddr():
    cmd_str = """
    ../target/release/substrate   \
        --base-path /tmp/node01   \
        --chain ./customSpecRaw.json   \
        --port %d   \
        --ws-port %d   \
        --rpc-port %d  \
        --validator   \
        --rpc-methods Unsafe   \
        --rpc-cors all \
        --name FirstNode
    """%(port_start, port_start+1, port_start+2)
    p_first = subprocess.Popen(cmd_str, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    close_fds=True, preexec_fn = os.setsid)
    out = ''
    while True:
        tmp = p_first.stdout.read(100)
        if len(tmp):
            out = out + tmp.decode('raw_unicode_escape')
            flag = 'Local node identity is: '
            index = out.find(flag)
            if index != -1 and len(out) > index + len(flag) + 53:
                rtn = out[index + len(flag): index + len(flag) + 53]
                #os.killpg(p_first.pid, signal.SIGUSR1)
                KillAllPid()
                return rtn

#启动主节点
def StartFirstNode():
    global pid_list
    args = ("""
        ../target/release/substrate   \
            --base-path /tmp/node01   \
            --chain ./customSpecRaw.json   \
            --port %d   \
            --ws-port %d   \
            --rpc-port %d  \
            --validator   \
            --rpc-methods Unsafe   \
            --rpc-cors all \
            --name FirstNode > ./logs/01.log 2>&1
    """%(port_start, port_start+1, port_start+2),)
    p = Process(target=os.system,args=args)
    p.start()
    pid_list.append(p)
    print("启动创世节点pid为:", p.pid)


#启动子节点
def StartSubNode(count, node_addr):
    global pid_list
    port_start_tmp = port_start + 3
    for idx in range(count):
        args = ("""../target/release/substrate   \
            --base-path /tmp/node%02d   \
            --chain ./customSpecRaw.json   \
            --port %d   \
            --ws-port %d   \
            --rpc-port %d   \
            --validator   \
            --rpc-methods Unsafe   \
            --name MyNode%02d   \
            --rpc-cors all \
            --bootnodes /ip4/127.0.0.1/tcp/%d/p2p/%s \
             > ./logs/%02d.log 2>&1"""%(
                idx+2, 
                port_start_tmp+idx*3+0, 
                port_start_tmp+idx*3+1, 
                port_start_tmp+idx*3+2,
                idx+2,
                port_start, 
                node_addr,
                idx+2
            ), )
        p = Process(target=os.system, args = args)
        p.start()
        pid_list.append(p)
        print("创建节点%d,pid为%d"%(idx+2, p.pid))

def SetKeys(arg):
    port_tmp = port_start+2
    for node_index, validator_item in enumerate(arg["validators"]):
        for curl_index in ["babe", "imol", "audi", "gran"]:
            cmd_str = """curl http://localhost:%d  -H "Content-Type:application/json;charset=utf-8" --data '{"jsonrpc":"2.0","id":1,"method":"author_insertKey","params": ["%s","%s","%s"]}' > /dev/null 2>&1"""\
                %(port_tmp + node_index * 3, 
                curl_index, 
                validator_item[2]["secret_phrase"],
                validator_item[2]["ed25519_pk"] if curl_index == "gran" else validator_item[2]["sr25519_pk"]
                )
            os.system(cmd_str)

def KillAllPid():
    global pid_list
    for item in pid_list:
        item.terminate()
    os.system("ps -ef | grep substrate | grep -v grep | awk '{print $2}'|xargs kill ")
    pid_list = []

def Exit(arg1, arg2):
    print(arg1, arg2)
    print("手动中断")
    KillAllPid()
    exit(0)

def InitSignal():
    pass
    # signal.signal(signal.SIGINT, Exit)
    # signal.signal(signal.SIGTERM, Exit)

def CreateNet():
    config_obj = {}
    print("""
    # =================================
    # 清空数据...
    # =================================""")
    Clear()
    print("""
    # =================================
    # 初始化创世文件...
    # =================================""")
    my_file = Path("./config.json")
    custom_arg = {}
    if my_file.is_file():
        print("配置文件已存在，使用之前的配置")
        json_file = open("./config.json", "r")
        custom_arg = json.load(json_file)["key"]
        json_file.close()
    else:
        print("""
        # =================================
        # 创建私钥...
        # =================================""")
        key_list = CreateKey(20)
        custom_arg = {
            "name": "BML Testnet",
            "id": "bml_testnet",
            "coin_config": {
                "tokenDecimals": 10,
                "tokenSymbol": "BML"
            },
            "balances": [#初始账户
                [key_list[0]["sr25519_addr"], 100000000*10**10], 
                [key_list[1]["sr25519_addr"], 200000000*10**10], 
                [key_list[2]["sr25519_addr"], 300000000*10**10], 
                [key_list[3]["sr25519_addr"], 400000000*10**10], 
                [key_list[4]["sr25519_addr"], 500000000*10**10], 
                [key_list[5]["sr25519_addr"], 600000000*10**10], 
                [key_list[6]["sr25519_addr"], 700000000*10**10], 
                [key_list[7]["sr25519_addr"], 800000000*10**10], 
                [key_list[8]["sr25519_addr"], 900000000*10**10], 
                [key_list[9]["sr25519_addr"], 1000000000*10**10],
                [key_list[10]["sr25519_addr"], 1100000000*10**10],
                [key_list[11]["sr25519_addr"], 12000000000*10**10],
                [key_list[12]["sr25519_addr"], 13000000000*10**10],
                [key_list[13]["sr25519_addr"], 14000000000*10**10],
                [key_list[14]["sr25519_addr"], 15000000000*10**10],
                [key_list[15]["sr25519_addr"], 16000000000*10**10],
                [key_list[16]["sr25519_addr"], 17000000000*10**10],
                [key_list[17]["sr25519_addr"], 18000000000*10**10],
                [key_list[18]["sr25519_addr"], 1900000000*10**10],
                [key_list[19]["sr25519_addr"], 2000000000*10**10]
            ],
            "validators": [# 验证人--验证人，控制人，回话
                [key_list[0],key_list[4], key_list[8], 100*10**10],
                [key_list[1],key_list[5], key_list[9], 200*10**10],
                [key_list[2],key_list[6], key_list[10], 300*10**10],
                [key_list[3],key_list[7], key_list[11], 300*10**10],
            ],
            "elections": [# 议会
                [key_list[10], 400*10**10],
                [key_list[11], 500*10**10],
                [key_list[12], 600*10**10],
            ],
            "society": [# 社区
                key_list[13],
                key_list[14],
                key_list[15]
            ],
            "tech": [# 技术委员会
                key_list[16],
                key_list[17],
                key_list[18]
            ],
            "sudo":key_list[19],
            "nft":key_list[19]
        }
    config_obj["key"] = custom_arg
    CreateCustomSpec(custom_arg)
    print("""
    # =================================
    # 初始化创世文件的raw...
    # =================================""")
    CreateRaw()
    InitSignal()
    
    print("""
    # =================================
    # 获取初始节点的地址
    # =================================""")
    node_addr = GetFirstNodeAddr()
    config_obj["addr"] = node_addr
    config_file = open("./config.json", "w")
    json.dump(config_obj, config_file, indent=2)
    config_file.close()
    print("节点地址为:",node_addr)
    
    print("""
    # =================================
    # 开始启动一共%d个节点
    # ================================="""%len(custom_arg["validators"]))
    StartFirstNode()
    #启动子节点
    StartSubNode(len(custom_arg["validators"]) - 1, node_addr)
    for i in range(20):
        print("等待节点启动完成%d..."%(19-i))
        time.sleep(1)
    print("""
    # =================================
    # 开始设置session key
    # =================================""")
    SetKeys(custom_arg)

    print("""
    # =================================
    # 关闭所有节点
    # =================================""")
    KillAllPid()
    # 启动所有节点
    StartNet()
    print("""
    # =================================
    # 等待退出
    # =================================""")
    for item in pid_list:
        item.join()
def StartNet():
    config_file = open("./config.json", "r")
    config_obj = json.load(config_file)
    print("""
    # =================================
    # 开始启动一共%d个节点
    # ================================="""%len(config_obj["key"]["validators"]))
    StartFirstNode()
    #启动子节点
    StartSubNode(len(config_obj["key"]["validators"])- 1, config_obj["addr"])
    print(pid_list)

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        if sys.argv[1] == "start":
            StartNet()
        elif sys.argv[1] == "create":
            CreateNet()
    else:
        msg= """\
=================================
python3 create_testnet.py create  ----->create testnet
python3 create_testnet.py start   ----->start testnet
=================================
        """
        print(msg)
    
