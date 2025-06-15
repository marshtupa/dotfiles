#!/usr/bin/env python3
"""
VPN Routes Collector
Собирает все маршруты, добавленные VPN-соединением
"""

import subprocess
import re
import json
import ipaddress
from datetime import datetime
from typing import List, Dict, Set

class VPNRoutesCollector:
    def __init__(self):
        self.routes = []
        self.vpn_interface = None
        self.vpn_gateway = None
        
    def find_vpn_interface(self) -> str:
        """Найти активный VPN интерфейс (utun)"""
        try:
            # Проверяем через scutil
            result = subprocess.run(
                ['scutil'], 
                input='show State:/Network/OpenVPN\n', 
                capture_output=True, 
                text=True
            )
            
            match = re.search(r'TunnelDevice\s*:\s*(\w+)', result.stdout)
            if match:
                self.vpn_interface = match.group(1)
                return self.vpn_interface
                
            # Альтернативный метод - ищем активные utun интерфейсы
            result = subprocess.run(['ifconfig'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'utun' in line and 'UP' in line:
                    self.vpn_interface = line.split(':')[0]
                    return self.vpn_interface
                    
        except Exception as e:
            print(f"Ошибка при поиске VPN интерфейса: {e}")
            
        return None
        
    def get_vpn_gateway(self) -> str:
        """Получить gateway VPN"""
        if not self.vpn_interface:
            return None
            
        try:
            result = subprocess.run(
                ['netstat', '-rn'], 
                capture_output=True, 
                text=True
            )
            
            for line in result.stdout.split('\n'):
                if self.vpn_interface in line:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].startswith('10.'):
                        self.vpn_gateway = parts[1]
                        return self.vpn_gateway
                        
        except Exception as e:
            print(f"Ошибка при получении gateway: {e}")
            
        return None
        
    def collect_routes_netstat(self) -> List[Dict]:
        """Собрать маршруты через netstat"""
        routes = []
        
        try:
            result = subprocess.run(
                ['netstat', '-rn', '-f', 'inet'], 
                capture_output=True, 
                text=True
            )
            
            for line in result.stdout.split('\n'):
                if self.vpn_gateway and self.vpn_gateway in line:
                    parts = line.split()
                    if len(parts) >= 3 and not line.startswith('default'):
                        network = parts[0]
                        gateway = parts[1]
                        netmask = parts[2] if not parts[2].startswith('U') else None
                        
                        if netmask and '.' in netmask:
                            try:
                                # Конвертируем в CIDR
                                cidr = sum(bin(int(x)).count('1') for x in netmask.split('.'))
                                routes.append({
                                    'network': network,
                                    'netmask': netmask,
                                    'cidr': cidr,
                                    'gateway': gateway,
                                    'interface': self.vpn_interface
                                })
                            except:
                                pass
                                
        except Exception as e:
            print(f"Ошибка при сборе маршрутов через netstat: {e}")
            
        return routes
        
    def collect_routes_from_log(self, log_path: str = None) -> List[Dict]:
        """Собрать маршруты из лога OpenVPN"""
        routes = []
        
        if not log_path:
            # Попробуем найти последний лог
            log_paths = [
                '/Library/Application Support/Tunnelblick/Logs/*.openvpn.log',
                '~/Library/Application Support/Tunnelblick/Logs/*.openvpn.log'
            ]
            
            import glob
            import os
            
            for path in log_paths:
                files = glob.glob(os.path.expanduser(path))
                if files:
                    log_path = max(files, key=os.path.getmtime)
                    break
                    
        if not log_path:
            return routes
            
        try:
            with open(log_path, 'r') as f:
                content = f.read()
                
            # Ищем PUSH_REPLY сообщения
            push_replies = re.findall(r'PUSH_REPLY[,:]([^\'"\n]+)', content)
            
            for reply in push_replies:
                # Извлекаем маршруты
                route_matches = re.findall(r'route\s+(\S+)\s+(\S+)', reply)
                for network, netmask in route_matches:
                    if network and netmask and '.' in netmask:
                        try:
                            cidr = sum(bin(int(x)).count('1') for x in netmask.split('.'))
                            routes.append({
                                'network': network,
                                'netmask': netmask,
                                'cidr': cidr,
                                'source': 'log'
                            })
                        except:
                            pass
                            
        except Exception as e:
            print(f"Ошибка при чтении лога: {e}")
            
        return routes
        
    def expand_network_to_ips(self, network: str, cidr: int) -> List[str]:
        """Развернуть сеть в список IP-адресов"""
        try:
            net = ipaddress.IPv4Network(f"{network}/{cidr}", strict=False)
            # Для больших сетей возвращаем только диапазон
            if net.num_addresses > 1024:
                return [f"{network}/{cidr} ({net.num_addresses} addresses)"]
            else:
                return [str(ip) for ip in net.hosts()]
        except:
            return []
            
    def collect_all_routes(self):
        """Собрать все маршруты из всех источников"""
        print("🔍 Поиск VPN интерфейса...")
        self.find_vpn_interface()
        
        if not self.vpn_interface:
            print("❌ VPN интерфейс не найден. Убедитесь, что VPN подключен.")
            return
            
        print(f"✅ Найден VPN интерфейс: {self.vpn_interface}")
        
        print("🔍 Получение VPN gateway...")
        self.get_vpn_gateway()
        
        if self.vpn_gateway:
            print(f"✅ VPN gateway: {self.vpn_gateway}")
        
        print("📊 Сбор маршрутов...")
        
        # Собираем из netstat
        routes_netstat = self.collect_routes_netstat()
        print(f"  - Найдено через netstat: {len(routes_netstat)} маршрутов")
        
        # Собираем из логов
        routes_log = self.collect_routes_from_log()
        print(f"  - Найдено в логах: {len(routes_log)} маршрутов")
        
        # Объединяем уникальные маршруты
        all_routes = {}
        for route in routes_netstat + routes_log:
            key = f"{route['network']}/{route.get('cidr', '?')}"
            all_routes[key] = route
            
        self.routes = list(all_routes.values())
        
    def save_results(self, format='all'):
        """Сохранить результаты в разных форматах"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Сортируем маршруты
        self.routes.sort(key=lambda x: (x.get('network', '').split('.'), x.get('cidr', 0)))
        
        # JSON формат
        if format in ['json', 'all']:
            with open(f'vpn_routes_{timestamp}.json', 'w') as f:
                json.dump({
                    'timestamp': timestamp,
                    'vpn_interface': self.vpn_interface,
                    'vpn_gateway': self.vpn_gateway,
                    'routes': self.routes
                }, f, indent=2)
                
        # Текстовый формат с CIDR нотацией
        if format in ['txt', 'all']:
            with open(f'vpn_routes_{timestamp}.txt', 'w') as f:
                f.write(f"# VPN Routes collected at {timestamp}\n")
                f.write(f"# VPN Interface: {self.vpn_interface}\n")
                f.write(f"# VPN Gateway: {self.vpn_gateway}\n\n")
                
                for route in self.routes:
                    f.write(f"{route['network']}/{route.get('cidr', '?')}\n")
                    
        # Скрипт для добавления маршрутов
        if format in ['sh', 'all']:
            with open(f'vpn_routes_{timestamp}.sh', 'w') as f:
                f.write("#!/bin/bash\n")
                f.write(f"# VPN Routes script generated at {timestamp}\n")
                f.write(f"# Usage: sudo ./vpn_routes_{timestamp}.sh add|delete\n\n")
                
                f.write("ACTION=${1:-add}\n")
                f.write(f"GATEWAY={self.vpn_gateway}\n\n")
                
                for route in self.routes:
                    f.write(f'route $ACTION -net {route["network"]} ')
                    f.write(f'-netmask {route.get("netmask", "255.255.255.0")} ')
                    f.write(f'$GATEWAY\n')
                    
            # Делаем скрипт исполняемым
            import os
            os.chmod(f'vpn_routes_{timestamp}.sh', 0o755)
            
    def print_summary(self):
        """Вывести сводку"""
        print("\n📋 СВОДКА:")
        print(f"Всего найдено маршрутов: {len(self.routes)}")
        
        # Подсчитываем общее количество IP
        total_ips = 0
        networks_by_size = {}
        
        for route in self.routes:
            try:
                cidr = route.get('cidr', 32)
                net = ipaddress.IPv4Network(f"{route['network']}/{cidr}", strict=False)
                total_ips += net.num_addresses
                
                size_key = f"/{cidr}"
                if size_key not in networks_by_size:
                    networks_by_size[size_key] = []
                networks_by_size[size_key].append(route['network'])
                
            except:
                pass
                
        print(f"\nОбщее количество IP-адресов: {total_ips:,}")
        
        print("\nРаспределение по размерам сетей:")
        for size, networks in sorted(networks_by_size.items()):
            print(f"  {size}: {len(networks)} сетей")
            
        print("\nПримеры найденных сетей:")
        for i, route in enumerate(self.routes[:10]):
            print(f"  - {route['network']}/{route.get('cidr', '?')}")
        if len(self.routes) > 10:
            print(f"  ... и еще {len(self.routes) - 10} маршрутов")


def main():
    print("🚀 VPN Routes Collector")
    print("=" * 50)
    
    collector = VPNRoutesCollector()
    collector.collect_all_routes()
    
    if collector.routes:
        collector.save_results('all')
        collector.print_summary()
        
        print("\n✅ Результаты сохранены в файлы:")
        print("  - vpn_routes_*.json - полная информация в JSON")
        print("  - vpn_routes_*.txt - список сетей в CIDR нотации")
        print("  - vpn_routes_*.sh - скрипт для ручного добавления маршрутов")
    else:
        print("\n❌ Маршруты не найдены. Проверьте подключение к VPN.")


if __name__ == "__main__":
    main()
