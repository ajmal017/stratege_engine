import logging
import logging.config
import os
import yaml

file_name = "log_config.yaml"
if os.path.exists(file_name):
    logging.config.dictConfig(yaml.load(open(file_name), Loader=yaml.SafeLoader))
else:
    logging.basicConfig(level=logging.INFO)
    logging.info("没有log的配置文件,将使用默认配置")



# def SetupLogger():
#     if not os.path.exists("log"):
#         os.makedirs("log")
#
#     time.strftime("application.%Y%m%d_%H%M%S.log")
#
#     recfmt = '(%(threadName)s) %(asctime)s.%(msecs)03d %(levelname)s %(filename)s:%(lineno)d %(message)s'
#     timefmt = '%y%m%d_%H:%M:%S'
#
#     # logging.basicConfig( level=logging.DEBUG,
#     #                    format=recfmt, datefmt=timefmt)
#     logging.basicConfig(filename=time.strftime("log/application.%y%m%d.log"),
#                         filemode="a",
#                         level=logging.INFO,
#                         format=recfmt, datefmt=timefmt)
#     logger = logging.getLogger()
#     console = logging.StreamHandler()
#     console.setFormatter(logging.Formatter(fmt=recfmt, datefmt=timefmt))
#     console.setLevel(logging.DEBUG)
#     logger.addHandler(console)
#
#
# SetupLogger()


# # 初始化依赖注入框架
# class MyBindingSpec(BindingSpec):
#     def configure(self, bind):
#         bind("config", to_instance=config, in_scope=pinject.SINGLETON)
#
#
# obj_graph = pinject.new_object_graph(modules=None, classes=[ConfigParser],
#                                      binding_specs=[MyBindingSpec()], only_use_explicit_bindings=True)
