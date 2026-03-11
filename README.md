# Sharing-bike

随着校园共享单车普及，出现了高峰时段局部区域车辆不足、非高峰区域车辆堆积、调度不及时等问题。传统人工转运方式效率低、成本高。本项目引入无人车自动调度模式，通过算法驱动实现共享单车的动态再平衡，最终达成： 实时掌握校园共享单车分布与使用状态 精准预测不同区域、不同时段的单车需求 自动规划最优调度路径，由无人车完成车辆转运 实现校园共享单车资源高效、均衡、智能化管理

使用方法：

在conda prompt中

**1、切盘**

```
e:
```

```
cd E:\Sharing bike\FleetPy-main\FleetPy-main
```

**2、激活环境**

```
conda activate fleetpy
```

**3、运行场景（已运行出结果，可跳过）**

```
python run_examples.py
```

这个脚本会运行一个或多个示例场景，并将结果保存到 `FleetPy/studies/example_study/results/ `目录下。

**4、测试-可视化模拟结果**

```
python replay_pyplot.py studies/example_study/results/<最新生成的仿真结果文件夹名称>
```
