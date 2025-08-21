from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import aiohttp
import asyncio
import os
import random
import time
import json
from dotenv import load_dotenv
from typing import Dict, List

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get API key from environment variable
API_KEY = os.getenv("IEX_KEY")

# Check if API key is available
if not API_KEY:
    print("WARNING: IEX_KEY environment variable is not set. Running in DEMO MODE with simulated data")
    DEMO_MODE = True
else:
    DEMO_MODE = False
    FINNHUB_WS_URL = f"wss://ws.finnhub.io?token={API_KEY}"
    COINAPI_WS_URL = f"wss://ws.coinapi.io/v1/"

import random
import time
from datetime import datetime

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_types: Dict[str, str] = {}  # 'stock' or 'crypto'

    async def connect(self, websocket: WebSocket, symbol: str, conn_type: str = 'stock'):
        await websocket.accept()
        self.active_connections[symbol] = websocket
        self.connection_types[symbol] = conn_type
        print(f"New {conn_type.upper()} WebSocket connection for {symbol}")

    def disconnect(self, symbol: str):
        if symbol in self.active_connections:
            conn_type = self.connection_types.get(symbol, 'stock')
            del self.active_connections[symbol]
            if symbol in self.connection_types:
                del self.connection_types[symbol]
            print(f"{conn_type.upper()} WebSocket connection closed for {symbol}")

    async def send_personal_message(self, message: str, symbol: str):
        if symbol in self.active_connections:
            await self.active_connections[symbol].send_text(message)

manager = ConnectionManager()

# WebSocket endpoint for market data (stocks and crypto)
@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str, is_crypto: bool = False):
    symbol = symbol.upper()
    conn_type = 'crypto' if is_crypto or symbol == 'BTC' else 'stock'
    print(f"{conn_type.upper()} WebSocket connection requested for symbol: {symbol}")
    
    await manager.connect(websocket, symbol, conn_type)
    print(f"{conn_type.upper()} WebSocket connection accepted for {symbol}")
    
    if DEMO_MODE:
        print(f"Running in DEMO MODE for {symbol} ({conn_type})")
        try:
            if conn_type == 'crypto':
                base_price = random.uniform(30000, 60000)  # Realistic BTC price range
            else:
                base_price = random.uniform(100, 200)  # Stock price range
                
            while True:
                # Check if connection is still active
                try:
                    # Simplified connection check - let the WebSocket error handling catch any issues
                    await websocket.send_json({"type": "ping"})
                    
                    # Generate new price data
                    price_change = random.uniform(-5, 5)
                    base_price = max(0.01, base_price + price_change)  # Ensure price doesn't go below 0.01
                    
                    # Format the response based on connection type
                    if conn_type == 'crypto':
                        response = {
                            "type": "trade",
                            "data": [{
                                "s": symbol,
                                "p": round(base_price, 2),
                                "t": int(time.time() * 1000),
                                "v": random.uniform(0.1, 10)
                            }]
                        }
                    else:  # stock
                        response = {
                            "type": "trade",
                            "data": [{
                                "s": symbol,
                                "p": round(base_price, 2),
                                "t": int(time.time() * 1000),
                                "v": random.randint(100, 10000)
                            }]
                        }
                    
                    await websocket.send_json(response)
                    await asyncio.sleep(1)  # Update every second
                    
                except WebSocketDisconnect:
                    print("Client disconnected")
                    break
                except Exception as e:
                    print(f"Error in demo mode: {e}")
                    break
                    
        except Exception as e:
            print(f"Error in demo mode: {e}")
            await websocket.send_json({"error": f"Demo mode error: {str(e)}"})
    else:
        print(f"Connecting to Finnhub WebSocket for {symbol}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(FINNHUB_WS_URL) as feed:
                    await feed.send_json({"type": "subscribe", "symbol": symbol})
                    
                    while True:
                        try:
                            msg = await feed.receive()
                            
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await websocket.send_text(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                error = feed.exception()
                                print(f"Finnhub WebSocket error: {error}")
                                await websocket.send_json({"error": str(error)})
                                break
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                print("Finnhub WebSocket connection closed")
                                break
                                
                        except WebSocketDisconnect:
                            print(f"Client {symbol} disconnected")
                            break
                            
                        except Exception as e:
                            print(f"Error in Finnhub WebSocket for {symbol}: {str(e)}")
                            try:
                                # Try to send the error message, but don't check the state
                                await websocket.send_json({"error": str(e)})
                            except Exception as send_error:
                                print(f"Error sending error message: {send_error}")
                            break
                            
        except Exception as e:
            print(f"Failed to connect to Finnhub WebSocket: {str(e)}")
            await websocket.send_json({"error": f"Failed to connect to market data: {str(e)}"})
    
    # Clean up
    manager.disconnect(symbol)
    try:
        data = await websocket.receive_text()
        print(f"Received message: {data}")
    except WebSocketDisconnect as e:
        print(f"WebSocket close: {e}")

# Serve the main HTML file
@app.get("/", response_class=HTMLResponse)
async def read_index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Stock Price Tracker</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            #stockData {
                margin-top: 20px;
                border: 1px solid #ddd;
                padding: 15px;
                border-radius: 5px;
            }
            .price-up { color: green; }
            .price-down { color: red; }
        </style>
    </head>
    <body>
        <h1>Stock Price Tracker</h1>
        <div>
            <div style="margin-bottom: 15px;">
                <label>
                    <input type="radio" name="assetType" value="stock" checked onchange="updateSymbolPlaceholder()">
                    Stock
                </label>
                <label style="margin-left: 15px;">
                    <input type="radio" name="assetType" value="crypto" onchange="updateSymbolPlaceholder()">
                    Cryptocurrency
                </label>
            </div>
            <div>
                <label for="symbol">Symbol: </label>
                <input type="text" id="symbol" placeholder="e.g. AAPL" />
                <button id="connectBtn" onclick="connectWebSocket()">Connect</button>
                <span id="status" style="margin-left: 10px;">Not connected</span>
            </div>
            <div id="suggestions" style="margin-top: 5px; font-size: 0.9em; color: #666;">
                Try: <a href="#" onclick="useExample('AAPL')">AAPL</a>,
                <a href="#" onclick="useExample('MSFT')">MSFT</a>,
                <a href="#" onclick="useExample('GOOGL')">GOOGL</a>,
                <a href="#" onclick="useExample('BTC', true)">BTC</a>,
                <a href="#" onclick="useExample('ETH', true)">ETH</a>
            </div>
        <div id="stockData">
            <p>Connect to see stock data...</p>
        </div>

        <script>
            let ws;
            let currentSymbol = '';
            let reconnectAttempts = 0;
            const MAX_RECONNECT_ATTEMPTS = 5;
            const RECONNECT_DELAY = 1000; // Start with 1 second
            let reconnectTimeout;
            let isCrypto = false;
            let explicitDisconnect = false; // Track if disconnect was user-initiated

            function updateStatus(message, isError = false) {
                const status = document.getElementById('status');
                status.textContent = message;
                status.style.color = isError ? 'red' : 'green';
                console.log(`Status: ${message}`);
            }

            function showError(message) {
                console.error(message);
                updateStatus(`Error: ${message}`, true);
                document.getElementById('stockData').innerHTML = `
                    <div class="error">
                        <p>${message}</p>
                        <p>Please try again or check the console for more details.</p>
                    </div>
                `;
            }

            function updateSymbolPlaceholder() {
                const symbolInput = document.getElementById('symbol');
                isCrypto = document.querySelector('input[name="assetType"]:checked').value === 'crypto';
                symbolInput.placeholder = isCrypto ? 'e.g. BTC' : 'e.g. AAPL';
                if (symbolInput.value === '') {
                    symbolInput.value = isCrypto ? 'BTC' : 'AAPL';
                }
            }

            function useExample(symbol, crypto = false) {
                document.getElementById('symbol').value = symbol;
                const radioBtn = document.querySelector(`input[value="${crypto ? 'crypto' : 'stock'}"]`);
                if (radioBtn) radioBtn.checked = true;
                updateSymbolPlaceholder();
                return false; // Prevent default link behavior
            }

            function connectWebSocket() {
                // Clear any existing reconnection attempts
                if (reconnectTimeout) {
                    clearTimeout(reconnectTimeout);
                    reconnectTimeout = null;
                }
                
                isCrypto = document.querySelector('input[name="assetType"]:checked').value === 'crypto';
                currentSymbol = document.getElementById('symbol').value.trim().toUpperCase() || (isCrypto ? 'BTC' : 'AAPL');
                
                updateStatus(`Connecting to ${currentSymbol} (${isCrypto ? 'Crypto' : 'Stock'})...`, 'info');
                document.getElementById('stockData').innerHTML = '<p>Connecting...</p>';
                
                // Close existing connection if any
                if (ws) {
                    try {
                        ws.onclose = null; // Prevent the close handler from triggering reconnection
                        ws.close();
                    } catch (e) {
                        console.log('Error closing existing connection:', e);
                    }
                }
                
                // Use the same protocol as the current page for WebSocket
                const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                // Use localhost explicitly to avoid any hostname resolution issues
                const endpoint = isCrypto || currentSymbol === 'BTC' ? 'crypto' : 'stock';
                const wsUrl = `${wsProtocol}//${window.location.hostname}:8003/ws/${currentSymbol}?is_crypto=${isCrypto}`;
                console.log('WebSocket URL:', wsUrl);
                
                try {
                    ws = new WebSocket(wsUrl);
                    
                    ws.onopen = () => {
                        console.log('WebSocket connection established');
                        reconnectAttempts = 0; // Reset reconnect attempts on successful connection
                        updateStatus(`Connected to ${currentSymbol} (${isCrypto ? 'Crypto' : 'Stock'})`, 'success');
                        
                        // Safely update the connect button if it exists
                        const connectBtn = document.getElementById('connectBtn');
                        if (connectBtn) {
                            connectBtn.textContent = 'Disconnect';
                            connectBtn.onclick = disconnectWebSocket;
                        }
                    };
                    
                    ws.onmessage = (event) => {
                        try {
                            const data = JSON.parse(event.data);
                            console.log('Received message:', data);
                            
                            // Handle ping-pong for connection health
                            if (data.type === 'ping') {
                                ws.send(JSON.stringify({ type: 'pong' }));
                                return;
                            }
                            
                            // Check for error messages
                            if (data.error) {
                                updateStatus(`Error: ${data.error}`, 'error');
                                return;
                            }
                            
                            // Process stock data
                            if (data.data && data.data.length > 0) {
                                const stock = data.data[0];
                                const price = parseFloat(stock.p).toFixed(2);
                                const volume = parseInt(stock.v).toLocaleString();
                                const timestamp = new Date(stock.t).toLocaleTimeString();
                                
                                // Determine if price went up or down
                                const priceElement = document.getElementById('currentPrice');
                                const oldPrice = parseFloat(priceElement?.textContent?.replace(/[^0-9.-]+/g,"") || '0');
                                const isUp = price > oldPrice;
                                
                                // Update UI
                                document.getElementById('stockSymbol').textContent = stock.s || symbol;
                                priceElement.textContent = `$${price}`;
                                priceElement.className = isUp ? 'price-up' : 'price-down';
                                
                                document.getElementById('volume').textContent = volume;
                                document.getElementById('lastUpdate').textContent = timestamp;
                                
                                // Add to price history for chart (if implemented)
                                if (typeof updatePriceHistory === 'function') {
                                    updatePriceHistory(parseFloat(price));
                                }
                            }
                        } catch (e) {
                            console.error('Error processing message:', e);
                            updateStatus(`Error processing data: ${e.message}`, 'error');
                        }
                    };
                    
                    ws.onclose = (event) => {
                        console.log('WebSocket connection closed:', event);
                        updateStatus(`Disconnected from ${currentSymbol}`, 'error');
                        
                        const connectBtn = document.getElementById('connectBtn');
                        if (connectBtn) {
                            connectBtn.textContent = 'Connect';
                            connectBtn.onclick = connectWebSocket;
                        }
                        
                        // Only attempt to reconnect if this wasn't an explicit disconnect
                        if (!explicitDisconnect) {
                            reconnectAttempts++;
                            if (reconnectAttempts <= MAX_RECONNECT_ATTEMPTS) {
                                const delay = Math.min(RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1), 30000);
                                updateStatus(`Connection lost. Reconnecting in ${delay/1000} seconds... (Attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`, 'warning');
                                
                                // Schedule reconnection
                                reconnectTimeout = setTimeout(() => {
                                    console.log(`Attempting to reconnect (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
                                    connectWebSocket();
                                }, delay);
                            } else {
                                updateStatus(`Failed to connect after ${MAX_RECONNECT_ATTEMPTS} attempts.`, 'error');
                            }
                        }
                        explicitDisconnect = false;
                    };
                    
                    ws.onerror = (error) => {
                        console.error('WebSocket error:', error);
                        updateStatus(`Connection error: ${error.message || 'Unknown error'}`, 'error');
                        // The onclose handler will be called after onerror
                    };
                    
                } catch (error) {
                    console.error('Error creating WebSocket:', error);
                    updateStatus(`Failed to connect: ${error.message}`, 'error');
                    
                    // Schedule reconnection attempt
                    reconnectAttempts++;
                    if (reconnectAttempts <= MAX_RECONNECT_ATTEMPTS) {
                        const delay = Math.min(RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1), 30000);
                        updateStatus(`Connection failed. Retrying in ${delay/1000} seconds... (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`, 'warning');
                        
                        reconnectTimeout = setTimeout(() => {
                            console.log(`Retrying connection (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
                            connectWebSocket();
                        }, delay);
                    } else {
                        updateStatus(`Max connection attempts (${MAX_RECONNECT_ATTEMPTS}) reached. Please check your connection and try again.`, 'error');
                    }
                }
            }

            function disconnectWebSocket() {
                if (ws) {
                    console.log('Closing WebSocket connection...');
                    explicitDisconnect = true; // Set flag before closing
                    ws.close();
                    ws = null;
                    updateStatus('Disconnected', 'info');
                }
            }

            window.onload = () => {
                console.log('Page loaded, connecting WebSocket...');
                connectWebSocket();
                
                // Auto-reconnect if connection is lost
                setInterval(() => {
                    if (!ws || ws.readyState === WebSocket.CLOSED) {
                        console.log('Connection lost, attempting to reconnect...');
                        connectWebSocket();
                    }
                }, 5000); // Check every 5 seconds
            };
        </script>
    </body>
    </html>
    """

# Start the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
