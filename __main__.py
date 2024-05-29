from fastapi import FastAPI
import uvicorn
import os
import docker
from pydantic import BaseModel
from fastapi.responses import PlainTextResponse
import random
import json

app = FastAPI()
client = docker.from_env()
image_name = "hadi1999/meta5_custom_minimal:1.4"
users_data_dir = "./data/users/"  # keep using / at end


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


def generate_random_port(start: int = 4000, end: int = 9999):
    unique = False
    while not unique:
        port = random.randint(start, end)
        unique = port not in get_allocated_ports()
    return port


def read_json_template(directory: str = '.', name: str = "config.json"):
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
    json_file_name = json_folder_dir + f"/{username}.json"
    os.makedirs(json_folder_dir, exist_ok=True)
    with open(json_file_name, "w") as file:
        file.write(json.dumps(json_data))
    return json_folder_dir


class User(BaseModel):
    username: str
    password: str
    balance: int = 1000
    phone: str | None = None
    email: str | None = None
    broker: str = "Amarkets-Demo"


@app.get("/")
async def root():
    return {"msg": "Welcome!"}


@app.post("/containers/create")
async def create_container(user: User):
    if not image_exists(image_name): build_image(image_name)
    port = generate_random_port()
    user_data = read_json_template()
    # ToDo: must edit userdata when selenium ran here
    login = "111111"
    password = "testPass"
    investor = "testInvestor"

    user_json_filepath = save_user_json_data(user_data, user.username)  # saves data of config for each user
    config_dir = "/config/.wine/drive_c/users/abc/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
    container = client.containers.run(image_name, auto_remove=True,
                                      name=user.username.replace(' ', '_'),
                                      detach=True, ports={3000: port},
                                      volumes=[f"{user_json_filepath}:{config_dir}"],
                                      environment={"CUSTOM_USER": user.username,
                                                   "PASSWORD": user.password})
    return {"msg": "mt5 container created",
            "ID": container.id,
            "user": {"username": user.username,
                     "balance": user.balance,
                     "mt5": {"login": login,
                             "password": password,
                             "investor": investor},
                     },
            "image": container.attrs['Config']['Image'],
            "port": port,
            "time_created": container.attrs["Created"]
            }


@app.get("/containers/logs/{id}")
def logs(id: str):
    return PlainTextResponse(client.containers.get(id).logs())


@app.delete("/containers/{id}")
def stop(id: str):
    container_ports = get_active_container_ports()
    client.containers.get(id).stop()
    return {"msg": f"container {id} stopped at port {container_ports.get(id, None)}",
            "ID": id,
            "port": container_ports.get(id, None)}


@app.get("/containers/")
def list_active_containers():
    c_ids = get_active_container_ports(True)
    return {"msg": "fetched active containers",
            "containers": c_ids}


@app.get("/containers/{id}")
def status(id: str):
    attrs = client.containers.get(id).attrs
    return {"msg": attrs}


if __name__ == "__main__":
    uvicorn.run(app=app, host="127.0.0.1", port=3000)
