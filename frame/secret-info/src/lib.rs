// This file is part of Substrate.

// Copyright (C) 2019-2022 Parity Technologies (UK) Ltd.
// SPDX-License-Identifier: Apache-2.0

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// 	http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! # Nicks Pallet
//!
//! - [`Config`]
//! - [`Call`]
//!
//! ## Overview
//!
//! Nicks is an example pallet for keeping track of account names on-chain. It makes no effort to
//! create a name hierarchy, be a DNS replacement or provide reverse lookups. Furthermore, the
//! weights attached to this pallet's dispatchable functions are for demonstration purposes only and
//! have not been designed to be economically secure. Do not use this pallet as-is in production.
//!
//! ## Interface
//!
//! ### Dispatchable Functions
//!
//! * `set_name` - Set the associated name of an account; a small deposit is reserved if not already
//!   taken.
//! * `clear_name` - Remove an account's associated name; the deposit is returned.
//! * `kill_name` - Forcibly remove the associated name; the deposit is lost.

#![cfg_attr(not(feature = "std"), no_std)]

use frame_support::traits::{Currency, OnUnbalanced, ReservableCurrency,ExistenceRequirement::{KeepAlive}};
pub use pallet::*;
use sp_runtime::traits::{StaticLookup, Zero, SaturatedConversion};
use sp_std::prelude::*;

type AccountIdOf<T> = <T as frame_system::Config>::AccountId;
type BalanceOf<T> = <<T as Config>::Currency as Currency<AccountIdOf<T>>>::Balance;
type NegativeImbalanceOf<T> =
	<<T as Config>::Currency as Currency<AccountIdOf<T>>>::NegativeImbalance;


#[frame_support::pallet]
pub mod pallet {
	use super::*;
	use frame_support::pallet_prelude::*;
	use frame_system::pallet_prelude::*;

	#[pallet::config]
	pub trait Config: frame_system::Config {
		/// The overarching event type.
		type Event: From<Event<Self>> + IsType<<Self as frame_system::Config>::Event>;

		/// The currency trait.
		type Currency: ReservableCurrency<Self::AccountId>;


		/// The origin which may forcibly set or remove a name. Root can always do this.
		type ForceOrigin: EnsureOrigin<Self::Origin>;


	}

	#[pallet::event]
	#[pallet::generate_deposit(pub(super) fn deposit_event)]
	pub enum Event<T: Config> {
		/// A name was set.
		NameSet { who: T::AccountId },
		/// A name was forcibly set.
		NameForced { target: T::AccountId },
		/// A name was changed.
		NameChanged { who: T::AccountId },
		/// A name was cleared, and the given balance returned.
		NameCleared { who: T::AccountId, deposit: BalanceOf<T> },
		/// A name was removed and the given balance slashed.
		NameKilled { target: T::AccountId, deposit: BalanceOf<T> },
	}

	/// Error for the nicks pallet.
	#[pallet::error]
	pub enum Error<T> {
		/// A name is too short.
		TooShort,
		/// A name is too long.
		TooLong,
		/// An account isn't named.
		Unnamed,
		/// Insufficient balance
		InsufficientBalance,
		FileExist,
		NoPower,
		FileNotExist,
	}
	
	#[pallet::storage]
	pub(super) type FileState<T: Config> =
		StorageMap<_, Twox64Concat, T::Hash, (u128/*size */,T::AccountId/*owner */, bool /*upload*/, bool /*ared */)>;

	/// price per byte
	#[pallet::storage]
	pub(super) type PriceOneByte<T: Config> =
		StorageValue<_, u128>;

	/// owner of module
	#[pallet::storage]
	pub(super) type FeeTo<T: Config> =
		StorageValue<_, T::AccountId>;

	#[pallet::storage]
	pub(super) type UpLoader<T: Config> =
		StorageValue<_, T::AccountId>;

	#[pallet::pallet]
	#[pallet::generate_store(pub(super) trait Store)]
	pub struct Pallet<T>(_);

	#[pallet::call]
	impl<T: Config> Pallet<T> {
		/// set the price of per byte
		#[pallet::weight(70_000_000)]
		pub fn set_1byte_price(origin: OriginFor<T>, price: u128) -> DispatchResult {
			ensure_root(origin)?;
			<PriceOneByte<T>>::put(price);
			Ok(())
		}

		#[pallet::weight(70_000_000)]
		pub fn force_set_fee_to(origin: OriginFor<T>, account: T::AccountId) -> DispatchResult {
			ensure_root(origin)?;
			<FeeTo<T>>::put(account);
			Ok(())
		}

		#[pallet::weight(70_000_000)]
		pub fn upload_file(origin: OriginFor<T>, file_hash: T::Hash, file_size: u128) -> DispatchResult {
			let sender = ensure_signed(origin)?;
			let price = <PriceOneByte<T>>::get().unwrap();
			let owner = <FeeTo<T>>::get().unwrap();
			let amount_need = price*file_size;
			// 判断资金够用
			if amount_need.saturated_into::<BalanceOf<T>>() > T::Currency::free_balance(&sender) - T::Currency::minimum_balance(){
				return Err(Error::<T>::InsufficientBalance.into());
			}
			// 判断文件拥有者正确且可上传
			// (u128/*size */,T::AccountId/*owner */, bool /*upload*/, bool /*ared */)
			match <FileState<T>>::get(file_hash) {
				Some(_) => {
					return Err(Error::<T>::FileExist.into());
				},
				None => {
					<FileState<T>>::insert(file_hash, (file_size, sender.clone(), false, false));
				} 
			};
			// 开始转账
			T::Currency::transfer(&sender, &owner, amount_need.saturated_into::<BalanceOf<T>>(), KeepAlive)?;
			Ok(())
		}

		/// 设置文件上传者
		#[pallet::weight(70_000_000)]
		pub fn force_set_uploader(origin: OriginFor<T>, uploader: T::AccountId) -> DispatchResult {
			ensure_root(origin)?;
			<UpLoader<T>>::put(uploader);
			Ok(())
		}

		/// 设置某个文件已经上传
		#[pallet::weight(70_000_000)]
		pub fn force_set_upload(origin: OriginFor<T>, file_hash: T::Hash) -> DispatchResult {
			ensure_root(origin.clone())?;
			let sender = ensure_signed(origin)?;
			let uploader = <UpLoader<T>>::get().unwrap();
			ensure!(sender == uploader, Error::<T>::NoPower);
			match <FileState<T>>::get(file_hash) {
				Some(v) => {
					let state = (v.0, v.1, true, v.3);
					<FileState<T>>::remove(file_hash);
					<FileState<T>>::insert(file_hash, state);
				},
				None => {
					return Err(Error::<T>::FileNotExist.into());
				}
			}
			Ok(())
		}

		/// 设置某个文件已经上传至ar
		#[pallet::weight(70_000_000)]
		pub fn force_set_upload_ar(origin: OriginFor<T>, file_hash: T::Hash) -> DispatchResult {
			ensure_root(origin.clone())?;
			let sender = ensure_signed(origin)?;
			let uploader = <UpLoader<T>>::get().unwrap();
			ensure!(sender == uploader, Error::<T>::NoPower);
			match <FileState<T>>::get(file_hash) {
				Some(v) => {
					let state = (v.0, v.1, v.2, true);
					<FileState<T>>::remove(file_hash);
					<FileState<T>>::insert(file_hash, state);
				},
				None => {
					return Err(Error::<T>::FileNotExist.into());
				}
			}
			Ok(())
		}
	}
}
