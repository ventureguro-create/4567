#!/usr/bin/env python3
"""
Backend API Testing for Telegram Geo-Radar MiniApp
Tests all geo-intel and miniapp endpoints
"""
import requests
import json
import sys
import uuid
from datetime import datetime

class GeoRadarAPITester:
    def __init__(self, base_url="https://9d9c303b-fa4e-4bb3-975f-22fe7bfee738.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_signal_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   {method} {endpoint}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    json_response = response.json()
                    print(f"   Response: {json.dumps(json_response, indent=2)[:200]}...")
                    return success, json_response
                except:
                    print(f"   Response: {response.text[:200]}...")
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:300]}...")
                return False, {}

        except requests.exceptions.Timeout:
            print(f"❌ Failed - Request timeout")
            return False, {}
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_geo_health(self):
        """Test geo module health check"""
        return self.run_test(
            "Geo Health Check",
            "GET", 
            "api/geo/health",
            200
        )

    def test_map_signals(self):
        """Test map signals endpoint"""
        return self.run_test(
            "Map Signals Endpoint", 
            "GET",
            "api/geo/map?days=7&limit=50",
            200
        )

    def test_miniapp_report_signal(self):
        """Test creating a new signal via miniapp"""
        test_signal = {
            "type": "police",
            "lat": 50.4501,
            "lng": 30.5234,
            "description": "Test police activity - automated test",
            "source": "miniapp",
            "userId": "test_user_12345",
            "username": "test_user"
        }
        
        success, response = self.run_test(
            "Create Signal via MiniApp",
            "POST",
            "api/geo/miniapp/report",
            200,
            data=test_signal
        )
        
        if success and response.get("ok") and response.get("signal"):
            self.test_signal_id = response["signal"]["id"]
            print(f"   Signal ID saved: {self.test_signal_id}")
        
        return success, response

    def test_vote_signal(self):
        """Test voting on a signal"""
        if not self.test_signal_id:
            print("❌ Skipping vote test - no signal ID available")
            return False, {}
        
        vote_data = {
            "vote": "confirm",
            "userId": "test_voter_67890"
        }
        
        return self.run_test(
            "Vote on Signal",
            "POST",
            f"api/geo/miniapp/signal/{self.test_signal_id}/vote",
            200,
            data=vote_data
        )

    def test_user_profile(self):
        """Test user profile endpoint"""
        test_user_id = "test_user_12345"
        return self.run_test(
            "User Profile",
            "GET",
            f"api/geo/miniapp/user/{test_user_id}/profile",
            200
        )

    def test_user_settings(self):
        """Test user privacy settings"""
        test_user_id = "test_user_12345"
        return self.run_test(
            "User Settings",
            "GET",
            f"api/geo/miniapp/user/{test_user_id}/settings",
            200
        )

    def test_additional_endpoints(self):
        """Test additional geo endpoints"""
        print("\n🔧 Testing Additional Endpoints...")
        
        # Test heatmap
        self.run_test(
            "Heatmap Data",
            "GET",
            "api/geo/heatmap?days=7",
            200
        )
        
        # Test top places
        self.run_test(
            "Top Places",
            "GET", 
            "api/geo/top?days=30&limit=10",
            200
        )
        
        # Test event types stats
        self.run_test(
            "Event Types Stats",
            "GET",
            "api/geo/event-types?days=30",
            200
        )

def main():
    print("🚀 Starting Telegram Geo-Radar Backend API Tests")
    print("=" * 60)
    
    tester = GeoRadarAPITester()
    
    # Core API tests
    print("\n📍 Core API Tests")
    tester.test_geo_health()
    tester.test_map_signals()
    
    # MiniApp specific tests
    print("\n📱 MiniApp API Tests")
    tester.test_miniapp_report_signal()
    tester.test_vote_signal()
    tester.test_user_profile() 
    tester.test_user_settings()
    
    # Additional endpoint tests
    tester.test_additional_endpoints()
    
    # Results summary
    print(f"\n📊 Test Results")
    print("=" * 40)
    print(f"Tests passed: {tester.tests_passed}/{tester.tests_run}")
    success_rate = (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0
    print(f"Success rate: {success_rate:.1f}%")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed - check logs above")
        return 1

if __name__ == "__main__":
    sys.exit(main())