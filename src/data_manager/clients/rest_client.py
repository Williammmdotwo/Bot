def fetch_positions(self):
        """Fetch open positions from OKX"""
        if not self.has_credentials:
            self.logger.warning("Cannot fetch positions: no API credentials available")
            return []

        try:
            self.logger.info("Fetching positions for account...")

            # 尝试获取持仓
            positions_response = self.exchange.fetch_positions()

            # 添加错误响应检查
            if not positions_response:
                self.logger.error("No positions response from exchange")
                return []

            # 处理响应
            positions = positions_response if isinstance(positions_response, list) else []

            self.logger.info(f"Successfully fetched {len(positions)} positions")
            return positions

        except Exception as e:
            self.logger.error(f"Failed to fetch positions: {e}")
            raise
