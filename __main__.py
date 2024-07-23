import time
from fastapi import FastAPI, HTTPException, BackgroundTasks
import uvicorn
import os
import docker
from docker import errors as DockerErrors
from pydantic import BaseModel
from fastapi.responses import PlainTextResponse
import random
import json
from typing import Annotated

app = FastAPI()
client = docker.from_env()
image_name = "hadi1999/meta5_custom_minimal:latest"
users_data_dir = "./data/users/"  # keep using / at end
HOST_IP = "51.89.168.20"

def build_image(image_name: str):
    image = client.images.pull(image_name)
    return image.short_id


def current_image_name_list() -> list[str]:
    name_list = [" ".join(image.attrs['RepoTags'])
                 for image in client.images.list()]
    return name_list


def image_exists(tag_name):
    return any([tag_name in img_name
                for img_name in current_image_name_list()])


def generate_random_port(start: int = 4000, end: int = 7000):
    unique = False
    while not unique:
        port = random.randint(start, end)
        unique = port not in get_allocated_ports()
    return port


def read_json_template(directory: str = '.', name: str = "ifund-config.json"):
    with open(f"{directory}/{name}", "r") as file:
        conf_dict = json.loads(file.read())
    return conf_dict


def get_allocated_ports():
    return list(get_active_container_ports().values())


def get_active_container_ids():
    return list(get_active_container_ports().keys())


def get_active_container_ports(
        to_list: bool = False):  # dict of containers by container id and port container_dict[id] = port
    container_dict = {}
    containers = client.containers.list()
    for c in containers:
        id = c.id
        container_port = None
        ports = c.ports
        for port in ports:
            if None in ports[port]: continue
            for p in ports[port]:
                if p["HostPort"].isdigit():
                    container_port = p["HostPort"]
                    break
            if container_port:
                container_dict[id] = container_port
                break
    if to_list:
        container_ls = [{"id": c_id, "port": port} for c_id, port in container_dict.items()]
        return container_ls
    return container_dict


def get_container_userpass_from_id(id: str):
    envs = client.containers.get(id).attrs["Config"]["Env"]
    password = [env.split('=')[1] for env in envs if "PASSWORD" in env][0]
    username = [env.split('=')[1] for env in envs if "CUSTOM_USER" in env][0]
    return {"username": username, "password": password}


########################### selenium functions ############
def run_selenium_pipeline(user_data: dict, broker: str,
                          url: str, username: str,
                          password: str, account_type="demo", delay=1):
    from Selenium.src import MT5_Manager
    mt5 = MT5_Manager(url, username, password)
    mt5.build_driver()
    mt5.init(delay=15)
    mt5.add_broker(broker=broker, delay=delay)
    mt5.create_new_account(user_data, type=account_type, broker=broker, delay=delay)
    #mt5.exit_update(delay = delay)
    #user_data = mt5.read_userdata(delay=delay, raise_empty= False)
    #mt5.exit_update()
    #mt5.login_account(delay=delay)
    #mt5.exit_update()
    #mt5.autotrade(reset=True, delay=delay)
    #mt5.activate_IFund_expert(delay=delay)
    #mt5.exit_update()
    #mt5.quit()
    #return user_data


def change_meta_account_password(old: str, new: str, url: str,
                                 container_username: str, container_password: str,
                                 delay=1):
    return
    from Selenium.src import MT5_Manager
    mt5 = MT5_Manager(url, container_username, container_password)
    mt5.build_driver()
    time.sleep(delay+4)
    mt5.exit_update()
    mt5.change_account_password(old, new, delay=delay)
    #mt5.quit()


def save_user_json_data(json_data: dict, username: str) -> str:
    """saves json file and returns it's rel path

    Args:
        json_data (dict)
        username (str)

    Returns:
        str: json file path
    """
    global users_data_dir
    json_folder_dir = os.path.abspath(users_data_dir + username)
    json_file_name = json_folder_dir + f"/ifund-config.json"
    os.makedirs(json_folder_dir, exist_ok=True)
    with open(json_file_name, "w") as file:
        file.write(json.dumps(json_data))
    return json_folder_dir


def read_user_json_data(username: str):
    global users_data_dir
    json_folder_dir = os.path.abspath(users_data_dir + username)
    json_file_name = json_folder_dir + f"/ifund-config.json"
    with open(json_file_name, 'r') as file:
        user_data_dict = json.loads(file.read())
    return user_data_dict


def rm_user_json_data(username: str):
    global users_data_dir
    json_folder_dir = os.path.abspath(users_data_dir + username)
    json_file_name = json_folder_dir + f"/ifund-config.json"
    os.remove(json_file_name)
    return True


def change_meta_account_invest_password(old, new):
    pass


def edit_user_json_data(username: str, edited_json: dict):
    user_data = read_user_json_data(username)
    save_user_json_data(edited_json, username)
    return True


class Mt5User(BaseModel):
    first_name: str
    second_name: str
    pre_phone: str = "+98"
    broker: str = "Amarkets-Demo"
    balance: int = 1000
    phone: str | None = None
    email: str | None = None
    account_type: str = "demo"


class User(BaseModel):
    username: str
    password: str
    broker_userdata: Mt5User


@app.get("/")
async def root():
    return {"msg": "Welcome!"}


@app.post("/containers/create")
async def create_container(user: User, bgts:BackgroundTasks, 
                           run_selenium: bool = True, delay: int = 10):
    print("\n\n")
    print(f"{user = }")
    run_selenium = False
    global HOST_IP
    if not image_exists(image_name):
        try:
            build_image(image_name)
        except DockerErrors.DockerException as e:
            if hasattr(e, "status_code") & hasattr(e, "response"):
                status_code, msg = e.status_code, e.response.json()["message"]
                raise HTTPException(status_code, msg)
        except Exception as e:
            status_code, msg = 520, f"Error: {e}"
            raise HTTPException(status_code, msg)

    port = generate_random_port()
    username = user.username.replace(' ', '_')
    ######################## defining initial json data #########
    user_data_json = read_json_template()
    user_data_json["Name"] = " ".join([user.broker_userdata.first_name,
                                       user.broker_userdata.second_name])
    user_data_json["Server"] = user.broker_userdata.broker
    user_data_json["Login"] = None
    user_data_json["Password"] = None
    user_data_json["Investor"] = None
    user_data_json["initial_balance"] = user.broker_userdata.balance
    user_json_filepath = save_user_json_data(user_data_json, username)  # saves data of config for each user
    config_dir = "/config/.wine/drive_c/users/abc/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
    #####################################
    try:
        container = client.containers.run(image_name, 
                                          restart_policy = {"Name": "always"},
                                          detach=True, ports={3000: port},
                                          mem_limit="1g",
                                          name=username,
                                          volumes=[f"{user_json_filepath}:{config_dir}"],
                                          environment={"CUSTOM_USER": username,
                                                       "PASSWORD": user.password})
    except DockerErrors.DockerException as e:
        if hasattr(e, "status_code") & hasattr(e, "response"):
            status_code, msg = e.status_code, e.response.json()["message"]
            raise HTTPException(status_code, msg)
    except Exception as e:
        status_code, msg = 520, f"Error: {e}"
        raise HTTPException(status_code, msg)
    ###### starting selenium process to make and login account
    if run_selenium:
        mt5_login = ''
        mt5_password = ''
        mt5_investor = ''
        _phone = str(user.broker_userdata.phone).replace('-', '')
        if _phone[0] == '0': _phone = _phone[1:]
        input_user_data = {"first_name": user.broker_userdata.first_name,
                           "second_name": user.broker_userdata.second_name,
                           "email": user.broker_userdata.email,
                           "phone": _phone,
                           "pre_phone": user.broker_userdata.pre_phone,
                           "deposit": str(user.broker_userdata.balance),
                           "broker": user.broker_userdata.broker.lower()
                            }

        print(f"\n{input_user_data = }\n")
        def selenium_task(user_data: dict, init_delay: float):
            time.sleep(init_delay)
            try:
                user_data = run_selenium_pipeline(user_data = user_data,
                                              broker = user.broker_userdata.broker, url = f"{HOST_IP}:{port}",
                                              username = user.username, password = user.password,
                                              account_type=user.broker_userdata.account_type, 
                                              delay = 1)
                mt5_login = user_data["Login"]
                mt5_password = user_data["Password"]
                mt5_investor = user_data["Investor"]
                # toDo: write these data to json file 
            except Exception as e:
                from warnings import warn
                mt5_login = ''
                mt5_password = ''
                mt5_investor = ''
                cid = container.id
                msg = f"\nexception {e}\n raised from selenium process at {cid}, ignoring\n"
                raise Exception(msg)
        # starting selenium process as bg task
        bgts.add_task(selenium_task, input_user_data, delay)
    else:
        mt5_login = ''
        mt5_password = ''
        mt5_investor = ''
    ########################## selenium process ended ##########
    user_data_json["Login"] = mt5_login
    user_data_json["Password"] = mt5_password
    user_data_json["Investor"] = mt5_investor
    user_data_json["initial_balance"] = user.broker_userdata.balance
    user_json_filepath = save_user_json_data(user_data_json, username)
    url = f"{HOST_IP}:{port}"
    password = user.password
    auth_url = f'http://{username}:{password}@{url}'
    print(f"{auth_url = }")
    return {"msg": "mt5 container created",
            "ID": container.id,
            "user": {"username": username,
                     "password": user.password,
                     "link": auth_url,
                     "balance": user.broker_userdata.balance,
                     "mt5": {
                         "login": mt5_login,
                         "password": mt5_password,
                         "investor": mt5_investor
                     }
                     },
            "image": container.attrs['Config']['Image'],
            "port": port,
            "time_created": container.attrs["Created"]
            }


@app.get("/containers/logs/{id}")
def logs(id: str):
    try:
        _logs = PlainTextResponse(client.containers.get(id).logs())
    except DockerErrors.DockerException as e:
        if hasattr(e, "status_code") & hasattr(e, "response"):
            status_code, msg = e.status_code, e.response.json()["message"]
            raise HTTPException(status_code, msg)
    except Exception as e:
        status_code, msg = 520, f"Error: {e}"
        raise HTTPException(status_code, msg)
    return _logs


@app.get("/containers/meta5/password/change/{id}")
def change_meta_password(id: str, old: str, new: str, bgts:BackgroundTasks, delay = 0.5):
    try:
        port = get_active_container_ports().get(id, None)
        login_data = get_container_userpass_from_id(id)
        username, password = login_data["username"], login_data["password"]
    except DockerErrors.DockerException as e:
        if hasattr(e, "status_code") & hasattr(e, "response"):
            status_code, msg = e.status_code, e.response.json()["message"]
            raise HTTPException(status_code, msg)
    except Exception as e:
        status_code, msg = 520, f"Error: {e}"
        raise HTTPException(status_code, msg)
    
    def task():
        global HOST_IP
        change_meta_account_password(old, new, f"{HOST_IP}:{port}",
                                    username, password, delay)
    bgts.add_task(task)
    return {"msg": f"password changed for container {id}"}


@app.delete("/containers/{id}")
def stop(id: str):
    try:
        container_ports = get_active_container_ports()
        client.containers.get(id).stop()
    except DockerErrors.DockerException as e:
        if hasattr(e, "status_code") & hasattr(e, "response"):
            status_code, msg = e.status_code, e.response.json()["message"]
            raise HTTPException(status_code, msg)
    except Exception as e:
        status_code, msg = 520, f"Error: {e}"
        raise HTTPException(status_code, msg)
    client.volumes.prune()
    client.containers.prune()
    return {"msg": f"container {id} stopped at port {container_ports.get(id, None)}",
            "ID": id,
            "port": container_ports.get(id, None)}


class UserExpertData(BaseModel):
    Name: str|None = None 
    Type: str = "Standard MT5 USD"
    Server: str|None = None
    Login: int | str | None = None
    Password: str|None = None
    Investor: str|None = None
    initial_balance: int|None = None
    auto_trade_check_period: int|None = None 
    gain_send_time_gmt: int|None = None
    max_total_dd: float|None = None
    max_daily_dd: float|None = None
    min_position_duration_seconds: int|None = None
    max_position_with_min_duration: int|None = None
    api_sandbox_mode: bool|None = None
    position_under_min: int | None = None
    total_position_under_min: int | None = None
    reset: bool|None = None


@app.put("/containers/edit/{id}")
def edit(id: str, json_data: UserExpertData):
    try:
        config_dir = "/config/.wine/drive_c/users/abc/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
        username = client.containers.get(id).name
    except DockerErrors.DockerException as e:
        if hasattr(e, "status_code") & hasattr(e, "response"):
            status_code, msg = e.status_code, e.response.json()["message"]
            raise HTTPException(status_code, msg)
    except Exception as e:
        status_code, msg = 520, f"Error: {e}"
        raise HTTPException(status_code, msg)
    json_data_user = read_user_json_data(username)
    json_data_dict = json_data.model_dump()
    new_json_data = {key: json_data_dict[key] 
                    if key in json_data_dict.keys() and json_data_dict[key] else json_data_user[key]
                    for key in json_data_user.keys()}
    rm_user_json_data(username)
    path = save_user_json_data(new_json_data, username)
    return {"msg": f"updated user data for {username}"}


@app.get("/containers/")
def list_active_containers():
    c_ids = get_active_container_ports(True)
    return {"msg": "fetched active containers",
            "containers": c_ids}


@app.get("/containers/{id}")
def status(id: str):
    try:
        state = client.containers.get(id).attrs["State"]
    except DockerErrors.DockerException as e:
        if hasattr(e, "status_code") & hasattr(e, "response"):
            status_code, msg = e.status_code, e.response.json()["message"]
            raise HTTPException(status_code, msg)
    except Exception as e:
        status_code, msg = 520, f"Error: {e}"
        raise HTTPException(status_code, msg)
    return {"msg": state}


if __name__ == "__main__":
    uvicorn.run(app=app, host="0.0.0.0", port=3000)

