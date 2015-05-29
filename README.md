# zha

zha is a small python library that delivers high availability to an arbitary program.
zha leverages Apache ZooKeeper and its python bindings kazoo, and is inspired from Apache Hadoop(ZKFC).

This project is WIP, no stable release yet.

## Concepts

- Small and Handy
- Well documented
- Customizable

## Install

```
sudo pip install kazoo
```

## Usage

Create a instance of `zha.ZHA` and call its method `mainloop()`.  See `skelton.py` for details. 
This is a standalone program to use zha.

## LICENCE

BSD
