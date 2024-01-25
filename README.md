# Chaos Engineering with LocalStack

This repository provides examples of different chaos engineering solutions using LocalStack.
It is meant to support the documentation user guide for chaos engineering: [http://docs.localstack.cloud/user-guide/chaos-engineering/](https://docs.localstack.cloud/user-guide/chaos-engineering/)

Chaos engineering with LocalStack presents a proactive approach to building resilient systems by introducing 
controlled disruptions. This versatile practice varies in its application; for software developers, it might 
mean application behavior and error handling, for architects, ensuring the robustness of system design, and for 
operations teams, examining the reliability of infrastructure provisioning. By integrating chaos experiments 
early in the development cycle, teams can uncover and address potential weaknesses, forging systems that 
withstand turbulent conditions. In this section’s subchapters, we will have a look at some of these scenarios 
using examples:

- Software behavior and error handling using Fault Injection Simulator experiments (FIS-experiments).
- Robust architecture as a result or Route53 failover tested with FIS experiments (route-53-failover).
- Infrastructure provisioning reliability when faced with outages and anomalies, as part of automated provisioning processes (extension-outages).
